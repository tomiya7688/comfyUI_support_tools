"""Shared resource arbitration, bounded stage execution, and cache policy."""

import argparse
import itertools
import logging
import math
import queue
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from dataclasses import asdict

from comfyui_support_tools.shared.contracts.resource_budget import (
    CancellationPolicy,
    ResourceBudget,
    ResourceBudgetOverride,
    ResourceKind,
    ResourceLease,
    ResourceStageMetrics,
)

DEFAULT_RESOURCE_BUDGET = ResourceBudget()
RESOURCE_FIELDS = tuple(asdict(DEFAULT_RESOURCE_BUDGET))
logger = logging.getLogger(__name__)


# {
#   責務: [ResourceBudgetCancelled: cooperative cancellationでqueue/lease待ちを終了する]
#   フィールド: [cancelの理由]
# }
class ResourceBudgetCancelled(RuntimeError):
    """Raised when a resource request or stage submission is cancelled."""


# {
#   責務: [ResourceBudgetUnavailable: bounded resource waitを受け付けられない状態を示す]
#   フィールド: [queue fullまたはtimeout理由]
# }
class ResourceBudgetUnavailable(RuntimeError):
    """Raised when a bounded resource wait queue is full or a wait times out."""


# {
#   責務: [ResourceBudgetManager: global/application/run budgetを階層解決してresource leaseを調停する]
#   フィールド: [global budget、scope利用数、pending waiters、condition]
# }
class ResourceBudgetManager:
    # {
    #   責務: [__init__: shared resource managerを初期化する]
    #   処理: [1: global/profile overrideを保存する 2: synchronized usage/waiter stateを作る]
    #   引数: [global_budget: default bounds, application_budgets: app overrides, fairness: priority wait policy]
    #   戻り値: []
    # }
    def __init__(
        self,
        global_budget: ResourceBudgetOverride | ResourceBudget | None = None,
        application_budgets: Mapping[str, ResourceBudgetOverride | ResourceBudget] | None = None,
    ):
        self._global = _as_override(global_budget or DEFAULT_RESOURCE_BUDGET)
        self._applications = {
            str(key): _as_override(value) for key, value in (application_budgets or {}).items()
        }
        self._condition = threading.Condition()
        self._used: dict[tuple[str, str, str], int] = {}
        self._waiters: dict[str, list[tuple[int, int, str]]] = {}
        self._waiter_scopes: dict[str, tuple[str, str]] = {}
        self._ticket = 0

    # {
    #   責務: [set_application_budget: application-specific overridesを設定/削除する]
    #   処理: [1: app IDを検証する 2: condition下でprofileを更新する]
    #   引数: [application_id: scope key, budget: partial override or None to clear]
    #   戻り値: []
    # }
    def set_application_budget(
        self, application_id: str, budget: ResourceBudgetOverride | ResourceBudget | None
    ) -> None:
        if not application_id.strip():
            raise ValueError("application_id is required")
        with self._condition:
            if budget is None:
                self._applications.pop(application_id, None)
            else:
                self._applications[application_id] = _as_override(budget)
            self._condition.notify_all()

    # {
    #   責務: [set_global_budget: shared hard budgetを更新する]
    #   処理: [1: overrideをvalidationする 2: condition下でglobal profileを更新する]
    #   引数: [budget: global hard budget profile]
    #   戻り値: []
    # }
    def set_global_budget(self, budget: ResourceBudgetOverride | ResourceBudget) -> None:
        override = _as_override(budget)
        with self._condition:
            self._global = override
            self._condition.notify_all()

    # {
    #   責務: [usage_snapshot: global/app/runの現在reservation数を返す]
    #   処理: [1: lock下でusage mappingのcopyを作る]
    #   引数: []
    #   戻り値: [usage: scope and resource usage metrics]
    # }
    def usage_snapshot(self) -> dict[tuple[str, str, str], int]:
        with self._condition:
            return dict(self._used)

    # {
    #   責務: [resolve: global/application/run profilesをsafe limitsへ解決する]
    #   処理: [1: fieldごとにrun -> app -> global -> safe default優先で選ぶ 2: ResourceBudgetを返す]
    #   引数: [application_id: application scope, run_budget: optional per-run override]
    #   戻り値: [budget: fully resolved limits]
    # }
    def resolve(
        self,
        application_id: str,
        run_budget: ResourceBudgetOverride | ResourceBudget | None = None,
    ) -> ResourceBudget:
        with self._condition:
            app_budget = self._applications.get(application_id, ResourceBudgetOverride())
            run = _as_override(run_budget) if run_budget is not None else ResourceBudgetOverride()
            values = {}
            for name in RESOURCE_FIELDS:
                values[name] = _first_value(
                    getattr(run, name),
                    getattr(app_budget, name),
                    getattr(self._global, name),
                    getattr(DEFAULT_RESOURCE_BUDGET, name),
                )
        return ResourceBudget(**values)

    # {
    #   責務: [acquire: global/application/run limitsを満たすまでresource unitsを待つ]
    #   処理: [1: waiterをpriority/FIFO順へ登録する 2: cancellation/capacityをpollする 3: leaseを返す]
    #   引数: [application_id: scope, run_id: run scope, resource: resource kind, units: requested units, run_budget: run override, cancellation: cancel event, priority: smaller is more urgent]
    #   戻り値: [lease: release可能な reservation]
    # }
    def acquire(
        self,
        application_id: str,
        run_id: str,
        resource: ResourceKind | str,
        units: int = 1,
        *,
        run_budget: ResourceBudgetOverride | ResourceBudget | None = None,
        cancellation: threading.Event | None = None,
        priority: int = 0,
        timeout: float | None = None,
    ) -> ResourceLease:
        kind = ResourceKind(resource)
        if (
            not isinstance(application_id, str)
            or not application_id.strip()
            or not isinstance(run_id, str)
            or not run_id.strip()
        ):
            raise ValueError("application_id and run_id are required")
        if type(units) is not int or units < 1:
            raise ValueError("units must be a positive integer")
        if type(priority) is not int:
            raise ValueError("priority must be an integer")
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise ValueError("timeout must be a nonnegative number or None")
        waiter_id = uuid.uuid4().hex
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            if not self._queue_has_capacity(application_id, run_id, run_budget):
                raise ResourceBudgetUnavailable("resource wait queue is full")
            self._ticket += 1
            ticket = self._ticket
            waiters = self._waiters.setdefault(kind.value, [])
            waiters.append((priority, ticket, waiter_id))
            self._waiter_scopes[waiter_id] = (application_id, run_id)
            waiters.sort()
            try:
                while True:
                    if cancellation is not None and cancellation.is_set():
                        raise ResourceBudgetCancelled("resource wait cancelled")
                    capacities = self._scope_capacities(application_id, run_budget, kind)
                    if any(capacity is not None and units > capacity for capacity in capacities):
                        raise ValueError(f"request exceeds {kind.value} budget")
                    if (
                        waiters
                        and waiters[0][2] == waiter_id
                        and self._has_capacity(application_id, run_id, kind, units, capacities)
                    ):
                        waiters.pop(0)
                        self._increment(application_id, run_id, kind, units)
                        self._condition.notify_all()
                        return ResourceLease(self, application_id, run_id, kind, units)
                    remaining = 0.05 if deadline is None else deadline - time.monotonic()
                    if remaining <= 0:
                        raise ResourceBudgetUnavailable("resource wait timed out")
                    self._condition.wait(min(remaining, 0.05))
            finally:
                self._waiters[kind.value] = [entry for entry in waiters if entry[2] != waiter_id]
                self._waiter_scopes.pop(waiter_id, None)
                self._condition.notify_all()

    # {
    #   責務: [try_acquire: resource slotを待たずに取得する]
    #   処理: [1: acquireをzero timeoutで呼ぶ 2: occupied/fullならNoneを返す]
    #   引数: [application_id/run_id/resource/units: request scope]
    #   戻り値: [lease: acquired lease or None]
    # }
    def try_acquire(
        self,
        application_id: str,
        run_id: str,
        resource: ResourceKind | str,
        units: int = 1,
    ) -> ResourceLease | None:
        try:
            return self.acquire(application_id, run_id, resource, units, timeout=0)
        except ResourceBudgetUnavailable:
            return None

    # {
    #   責務: [_queue_has_capacity: global/application/runのpending queue上限を確認する]
    #   処理: [1: 各scopeのqueue capを解決する 2: pending countと比較する]
    #   引数: [application_id/run_id: request scope, run_budget: run profile]
    #   戻り値: [available: bounded waiter queueに追加可能か]
    # }
    def _queue_has_capacity(self, application_id, run_id, run_budget) -> bool:
        global_limit = self._global.queue_capacity or DEFAULT_RESOURCE_BUDGET.queue_capacity
        app_limit = self._applications.get(application_id, ResourceBudgetOverride()).queue_capacity
        run_limit = _as_override(run_budget).queue_capacity if run_budget is not None else None
        app_limit = app_limit if app_limit is not None else global_limit
        run_limit = run_limit if run_limit is not None else app_limit
        scoped_run_id = (application_id, run_id)
        app_waiters = sum(scope[0] == application_id for scope in self._waiter_scopes.values())
        run_waiters = sum(scope == scoped_run_id for scope in self._waiter_scopes.values())
        return (
            len(self._waiter_scopes) < global_limit
            and app_waiters < app_limit
            and run_waiters < run_limit
        )

    # {
    #   責務: [_has_capacity: global/app/run usageがeffective limit内か確認する]
    #   処理: [1: scope countersを読む 2: resource capacityと比較する]
    #   引数: [application_id/run_id/resource/units/budget: pending request context]
    #   戻り値: [available: reservation可能ならtrue]
    # }
    def _has_capacity(self, application_id, run_id, resource, units, budget) -> bool:
        global_used = self._used.get(("global", "", resource.value), 0)
        application_used = self._used.get(("application", application_id, resource.value), 0)
        run_used = self._used.get(("run", f"{application_id}:{run_id}", resource.value), 0)
        return all(
            capacity is None or used + units <= capacity
            for used, capacity in zip(
                (global_used, application_used, run_used), budget, strict=True
            )
        )

    # {
    #   責務: [_scope_capacities: global capとapp/run override capsを分離して解決する]
    #   処理: [1: 各scopeのconfigured valueを読む 2: lower scopeへsafe fallbackする]
    #   引数: [application_id: app key, run_budget: run override, resource: resource kind]
    #   戻り値: [capacities: global/app/run hard limits]
    # }
    def _scope_capacities(self, application_id, run_budget, resource):
        with self._condition:
            global_capacity = getattr(self._global, resource.value)
            if global_capacity is None:
                global_capacity = getattr(DEFAULT_RESOURCE_BUDGET, resource.value)
            app_profile = self._applications.get(application_id, ResourceBudgetOverride())
            application_capacity = getattr(app_profile, resource.value)
            if application_capacity is None:
                application_capacity = global_capacity
            run_profile = (
                _as_override(run_budget) if run_budget is not None else ResourceBudgetOverride()
            )
            run_capacity = getattr(run_profile, resource.value)
            if run_capacity is None:
                run_capacity = application_capacity
        return global_capacity, application_capacity, run_capacity

    # {
    #   責務: [_increment: reservation unitsをglobal/application/run scopeへ加算する]
    #   処理: [1: three scope keysを作る 2: usage countを加算する]
    #   引数: [application_id/run_id/resource/units: acquired request]
    #   戻り値: []
    # }
    def _increment(self, application_id, run_id, resource, units) -> None:
        keys = (
            ("global", "", resource.value),
            ("application", application_id, resource.value),
            ("run", f"{application_id}:{run_id}", resource.value),
        )
        for key in keys:
            self._used[key] = self._used.get(key, 0) + units

    # {
    #   責務: [_release: scope usageを返却してwaiterを起こす]
    #   処理: [1: scopeごとのunitsを減らす 2: condition waitersを通知する]
    #   引数: [application_id/run_id/resource/units: released reservation]
    #   戻り値: []
    # }
    def _release(self, application_id, run_id, resource, units) -> None:
        keys = (
            ("global", "", resource.value),
            ("application", application_id, resource.value),
            ("run", f"{application_id}:{run_id}", resource.value),
        )
        with self._condition:
            for key in keys:
                remaining = self._used.get(key, 0) - units
                if remaining < 0:
                    raise RuntimeError("resource lease released more than once")
                if remaining:
                    self._used[key] = remaining
                else:
                    self._used.pop(key, None)
            self._condition.notify_all()


# {
#   責務: [BoundedResourceStage: bounded input queueとstage-specific worker/resource limitを実行する]
#   フィールド: [queue、workers、cancel state、handler、metrics、optional next stage]
# }
class BoundedResourceStage:
    # {
    #   責務: [__init__: bounded stageを起動してresource profileへ接続する]
    #   処理: [1: limitsを検証する 2: bounded queueを作る 3: worker threadを起動する]
    #   引数: [name: stage name, handler: task processor(item, cancellation), manager: shared resource manager, application_id/run_id: scopes, resource: primary limited resource, resource_units: primary per-task demand, resource_requirements: additional demands such as VRAM with GPU jobs, concurrency: workers, queue_capacity: bounded pending items, budget: optional per-run override, cancellation: shared job token, downstream: next bounded stage, degrade_after_oom: one optional fallback, on_error: terminal task error hook]
    #   戻り値: []
    # }
    def __init__(
        self,
        name: str,
        handler: Callable,
        manager: ResourceBudgetManager,
        application_id: str,
        run_id: str,
        resource: ResourceKind | str,
        *,
        resource_units: int = 1,
        resource_requirements: Mapping[ResourceKind | str, int] | None = None,
        concurrency: int | None = None,
        queue_capacity: int | None = None,
        budget: ResourceBudgetOverride | ResourceBudget | None = None,
        cancellation: threading.Event | None = None,
        downstream: "BoundedResourceStage | None" = None,
        degrade_after_oom: Callable | None = None,
        on_error: Callable | None = None,
    ):
        if not name.strip() or not callable(handler):
            raise ValueError("stage name and handler are required")
        resolved_budget = manager.resolve(application_id, budget)
        resource_limit = getattr(resolved_budget, ResourceKind(resource).value)
        if type(resource_units) is not int or resource_units < 1:
            raise ValueError("resource_units must be a positive integer")
        requirements = {ResourceKind(resource): resource_units}
        for kind, units in (resource_requirements or {}).items():
            normalized_kind = ResourceKind(kind)
            if normalized_kind in requirements:
                raise ValueError("resource_requirements must not repeat the primary resource")
            if type(units) is not int or units < 1:
                raise ValueError("resource requirement units must be positive integers")
            requirements[normalized_kind] = units
        if concurrency is None:
            concurrency = (
                1
                if ResourceKind(resource) in {ResourceKind.VRAM_MB, ResourceKind.RAM_MB}
                else min(resource_limit or 1, 32)
            )
        elif resource_limit is not None:
            concurrency = min(concurrency, max(1, resource_limit // resource_units))
        if queue_capacity is None:
            queue_capacity = resolved_budget.queue_capacity
        if type(concurrency) is not int or not 1 <= concurrency <= 32:
            raise ValueError("concurrency must be in 1..32")
        if type(queue_capacity) is not int or queue_capacity < 1:
            raise ValueError("queue_capacity must be a positive integer")
        self.name = name
        self.handler = handler
        self.manager = manager
        self.application_id = application_id
        self.run_id = run_id
        self.resource = ResourceKind(resource)
        self.resource_units = resource_units
        self.resource_requirements = tuple(
            sorted(
                requirements.items(),
                key=lambda item: (
                    item[0] not in {ResourceKind.VRAM_MB, ResourceKind.RAM_MB},
                    item[0].value,
                ),
            )
        )
        self.concurrency = concurrency
        self._queue = queue.PriorityQueue(maxsize=queue_capacity)
        self._cancellation = cancellation or threading.Event()
        self._downstream = downstream
        self._budget = budget
        self._default_priority = resolved_budget.priority
        self._cancellation_policy = resolved_budget.cancellation_policy
        self._stopping = threading.Event()
        self._degrade_after_oom = degrade_after_oom
        self._on_error = on_error
        self._lock = threading.Lock()
        self._counts = {key: 0 for key in ResourceStageMetrics.__dataclass_fields__}
        self._sequence = itertools.count()
        self._threads = [
            threading.Thread(target=self._work, name=f"resource-{name}-{index}", daemon=True)
            for index in range(concurrency)
        ]
        for worker in self._threads:
            worker.start()

    # {
    #   責務: [submit: itemをbounded queueへputしてbackpressure/cancellationを適用する]
    #   処理: [1: cancellationを検査する 2: nonblocking pollingでputする 3: wait metricを更新する]
    #   引数: [item: stage input]
    #   戻り値: [accepted: accepted status]
    # }
    def submit(self, item, *, priority: int | None = None) -> bool:
        priority = self._default_priority if priority is None else priority
        if type(priority) is not int:
            raise ValueError("priority must be an integer")
        while True:
            if self._stopping.is_set() or self._cancellation.is_set():
                raise ResourceBudgetCancelled(f"stage {self.name} is cancelled")
            try:
                self._queue.put((priority, next(self._sequence), item), timeout=0.05)
                self._count("submitted")
                return True
            except queue.Full:
                self._count("backpressure_waits")

    # {
    #   責務: [cancel: stage ingressを止めてqueued itemを明示的に破棄する]
    #   処理: [1: cancel eventをsetする 2: queued entriesを取り出してtask_doneする]
    #   引数: []
    #   戻り値: [discarded: cancelled pending entries]
    # }
    def cancel(self, policy: CancellationPolicy | str | None = None) -> int:
        cancellation_policy = (
            self._cancellation_policy if policy is None else CancellationPolicy(policy)
        )
        self._stopping.set()
        if cancellation_policy is CancellationPolicy.CANCEL_PENDING:
            self._cancellation.set()
        if self._downstream is not None:
            self._downstream.cancel(cancellation_policy)
        discarded = 0
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            else:
                self._queue.task_done()
                discarded += 1
        with self._lock:
            self._counts["cancelled"] += discarded
        return discarded

    # {
    #   責務: [close: ingressを停止してworker threadを終了させる]
    #   処理: [1: pending workをcancelする 2: worker sentinelを投入する 3: workerをjoinする]
    #   引数: [timeout: worker join timeout seconds]
    #   戻り値: [stopped: 全workerが終了したか]
    # }
    def close(self, timeout: float = 2.0) -> bool:
        self.cancel()
        deadline = time.monotonic() + max(0.0, timeout)
        for _worker in self._threads:
            try:
                self._queue.put(
                    (2**63 - 1, next(self._sequence), None),
                    timeout=max(0.0, deadline - time.monotonic()),
                )
            except queue.Full:
                return False
        for worker in self._threads:
            worker.join(max(0.0, deadline - time.monotonic()))
        return all(not worker.is_alive() for worker in self._threads)

    # {
    #   責務: [join: 現在投入済みstage workの完了を待つ]
    #   処理: [1: queue task accountingをjoinする]
    #   引数: []
    #   戻り値: []
    # }
    def join(self) -> None:
        self._queue.join()

    # {
    #   責務: [metrics: immutable current stage countersを返す]
    #   処理: [1: lock下でcounter snapshotを作る]
    #   引数: []
    #   戻り値: [metrics: stage counters]
    # }
    def metrics(self) -> ResourceStageMetrics:
        with self._lock:
            return ResourceStageMetrics(**self._counts)

    # {
    #   責務: [_work: queueからworkを取りResource lease中に処理する]
    #   処理: [1: itemを取得する 2: budget lease取得 3: handler/degrade/downstreamを動かす 4: metricsを更新しtaskを閉じる]
    #   引数: []
    #   戻り値: []
    # }
    def _work(self) -> None:
        while True:
            entry = self._queue.get()
            try:
                _priority, _sequence, item = entry
                if item is None:
                    return
                if self._stopping.is_set() or self._cancellation.is_set():
                    self._count("cancelled")
                    continue
                resolved = self.manager.resolve(self.application_id, self._budget)
                stage_limit = min(
                    self.concurrency, getattr(resolved, self.resource.value) or self.concurrency
                )
                if stage_limit < 1:
                    raise RuntimeError("resolved stage resource limit is zero")
                try:
                    with ExitStack() as leases:
                        for kind, units in self.resource_requirements:
                            leases.enter_context(
                                self.manager.acquire(
                                    self.application_id,
                                    self.run_id,
                                    kind,
                                    units,
                                    run_budget=self._budget,
                                    cancellation=self._cancellation,
                                    priority=_priority,
                                )
                            )
                        result = self.handler(item, self._cancellation)
                except MemoryError:
                    if self._degrade_after_oom is None:
                        raise
                    self._count("degraded_after_oom")
                    result = self._degrade_after_oom(item, self._cancellation)
                if self._downstream is not None and result is not None:
                    self._downstream.submit(result, priority=_priority)
                self._count("completed")
            except ResourceBudgetCancelled:
                self._count("cancelled")
            except Exception as error:
                self._count("failed")
                if self._on_error is not None:
                    try:
                        self._on_error(item, error)
                    except Exception as hook_error:
                        logger.error(
                            "Resource stage %s error hook failed: %s",
                            self.name,
                            type(hook_error).__name__,
                        )
                else:
                    logger.error("Resource stage %s failed: %s", self.name, type(error).__name__)
            finally:
                self._queue.task_done()

    # {
    #   責務: [_count: stage metric counterをthread safeに更新する]
    #   処理: [1: lock下でcounterをincrementする]
    #   引数: [name: metric field]
    #   戻り値: []
    # }
    def _count(self, name: str) -> None:
        with self._lock:
            self._counts[name] += 1


# {
#   責務: [add_resource_budget_arguments: CLI parserへ共通resource override flagsを登録する]
#   処理: [1: ResourceBudget fieldsをoptional CLI argumentsへ追加する]
#   引数: [parser: application-specific argument parser]
#   戻り値: []
# }
def add_resource_budget_arguments(parser: argparse.ArgumentParser) -> None:
    options = (
        ("cpu-threads", "cpu_threads"),
        ("cpu-processes", "cpu_processes"),
        ("gpu-jobs", "gpu_jobs"),
        ("vram-budget-mb", "vram_budget_mb"),
        ("ram-budget-mb", "ram_budget_mb"),
        ("disk-io-jobs", "disk_io_jobs"),
        ("network-jobs", "network_jobs"),
        ("external-api-concurrency", "external_api_concurrency"),
        ("queue-capacity", "queue_capacity"),
        ("priority", "priority"),
    )
    for option, destination in options:
        parser.add_argument(f"--{option}", dest=destination, type=int, default=None)
    parser.add_argument(
        "--cancellation-policy",
        choices=tuple(policy.value for policy in CancellationPolicy),
        default=None,
    )


# {
#   責務: [resolve_resource_budget_options: CLI argsをvalidated partial budgetへ変換する]
#   処理: [1: known resource fieldsを読み取る 2: positive integer rulesを検証する]
#   引数: [arguments: parsed argparse namespace]
#   戻り値: [budget: optional CLI overrides]
# }
def resolve_resource_budget_options(arguments) -> ResourceBudgetOverride:
    values = {
        name: getattr(arguments, name, None)
        for name in RESOURCE_FIELDS
        if getattr(arguments, name, None) is not None
    }
    return _as_override(ResourceBudgetOverride(**values))


# {
#   責務: [_as_override: concrete budgetをoptional field overrideへ正規化する]
#   処理: [1: dataclass mappingを作る 2: ResourceBudgetOverrideへ変換する]
#   引数: [budget: concrete or partial profile]
#   戻り値: [override: fieldwise profile]
# }
def _as_override(budget) -> ResourceBudgetOverride:
    if isinstance(budget, ResourceBudgetOverride):
        override = budget
    elif isinstance(budget, ResourceBudget):
        override = ResourceBudgetOverride(**asdict(budget))
    else:
        raise TypeError("budget must be ResourceBudget or ResourceBudgetOverride")
    values = asdict(override)
    for name, value in values.items():
        if name == "cancellation_policy":
            if value is not None:
                try:
                    values[name] = CancellationPolicy(value)
                except ValueError as error:
                    raise ValueError("cancellation_policy is invalid") from error
        elif name == "priority":
            if value is not None and type(value) is not int:
                raise ValueError("priority must be an integer")
        elif value is not None and (type(value) is not int or value < 1):
            raise ValueError(f"{name} must be None or a positive integer")
    return ResourceBudgetOverride(**values)


# {
#   責務: [_first_value: first configured optional budget valueを選択する]
#   処理: [1: candidate hierarchyを走査する 2: first non-Noneを返す]
#   引数: [values: ordered profile fields]
#   戻り値: [value: resolved field]
# }
def _first_value(*values):
    for value in values:
        if value is not None:
            return value
    return None


GLOBAL_RESOURCE_BUDGET_MANAGER = ResourceBudgetManager()
