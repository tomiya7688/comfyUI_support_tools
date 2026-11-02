"""Thread-safe bounded job runtime shared by local IO adapters.

Workers register a job, then wait for a concurrency slot. The runtime never
executes backend-specific work itself and never touches Tk.
"""

import math
from collections import deque
from threading import Condition, Event
import time
import uuid

from comfyui_support_tools.shared.contracts.job_contracts import (
    CancelCapability,
    CheckpointCapability,
    ACTIVE_JOB_STATES,
    JobSnapshot,
    PartialResultPolicy,
    ShutdownPolicy,
    TERMINAL_JOB_STATES,
)
from comfyui_support_tools.shared.job_snapshot_store import JobSnapshotStore
from comfyui_support_tools.applications.main_gui.data.processing.job_runtime_control import (
    JobRuntimeControlMixin,
)
from comfyui_support_tools.applications.main_gui.data.processing.job_runtime_models import (
    MAX_LOG_CHARS,
    MAX_LOG_LINES,
    MAX_SOURCES,
    CancelHandler,
    ResumeHandler,
    RetryHandler,
    _JobRecord,
)
from comfyui_support_tools.shared.contracts.resource_budget import ResourceKind, ResourceLease
from comfyui_support_tools.shared.resource_budget import ResourceBudgetManager


# {
#   責務: [JobRuntime: bounded job lifecycleと外部backend停止要求を管理する]
#   フィールド: [各Jobの状態、queue、cancel Event、backend cancel handler]
#   処理: [開始slot、進捗、terminal state、cooperative cancelを同期する]
# }
class JobRuntime(JobRuntimeControlMixin):
    # {
    #   責務: [__init__: bounded Job runtimeを初期化しpersisted historyを復元する]
    #   処理: [1: concurrency/history制限を検証する 2: runtime stateを初期化する 3: storeからsnapshotを復旧する]
    #   引数: [max_concurrent: 最大同時Job数, history_limit: 保存履歴数, store: optional durable snapshot store]
    #   戻り値: []
    # }
    def __init__(
        self,
        max_concurrent: int = 2,
        history_limit: int = 100,
        store: JobSnapshotStore | None = None,
        resource_manager: ResourceBudgetManager | None = None,
        application_id: str = "main-gui",
        resource_kind: ResourceKind | str = ResourceKind.CPU_PROCESSES,
        resource_units: int = 1,
    ):
        if not 1 <= max_concurrent <= 16:
            raise ValueError("max_concurrent must be 1..16")
        if not 10 <= history_limit <= 1000:
            raise ValueError("history_limit must be 10..1000")
        if not isinstance(application_id, str) or not application_id.strip():
            raise ValueError("application_id is required")
        if type(resource_units) is not int or resource_units < 1:
            raise ValueError("resource_units must be a positive integer")
        self.max_concurrent = max_concurrent
        self.history_limit = history_limit
        self._resource_manager = resource_manager
        self._resource_application_id = application_id
        self._resource_kind = ResourceKind(resource_kind)
        self._resource_units = resource_units
        self._resource_leases: dict[str, ResourceLease] = {}
        self._store = store
        self._condition = Condition()
        self._records: dict[str, _JobRecord] = {}
        self._queue: deque[str] = deque()
        self._running: set[str] = set()
        self._attached_workers: set[str] = set()
        self._cancel: dict[str, Event] = {}
        self._cancel_requested: set[str] = set()
        self._backend_cancel_handlers: dict[str, CancelHandler] = {}
        self._finish_after_item: set[str] = set()
        self._resume_handlers: dict[str, ResumeHandler] = {}
        self._retry_handlers: dict[str, RetryHandler] = {}
        self._retry_inflight: set[str] = set()
        self._closed = False
        self._sequence = 0
        if self._store is not None:
            self._restore_locked()

    # {
    #   責務: [create: capabilityとmanifest参照を持つbounded Jobを作る]
    #   処理: [1: request metadataを検証する 2: Job recordとcancel Eventを作る 3: queue/storeへ保存する]
    #   引数: [kind: Job種類, action: 表示名, source_ids: 入力ID, source_names: 表示名, cancel_event: adapter token, backend_job_id: 外部ID, retryable: retry可否, retry_of: parent ID, cancel_capability: cancel方式, checkpoint_capability: checkpoint粒度, checkpoint_ref: 再開ref, shutdown_policy: 終了方針, partial_result_policy: 部分成果物方針, operation_id: idempotency ID, manifest_ref: 永続manifest ref]
    #   戻り値: [job_id: 新規Job ID]
    # }
    def create(
        self,
        kind: str,
        action: str,
        *,
        source_ids=(),
        source_names=(),
        cancel_event: Event | None = None,
        backend_job_id: str = "",
        retryable: bool = False,
        retry_of: str = "",
        cancel_capability: CancelCapability | str = CancelCapability.COOPERATIVE,
        checkpoint_capability: CheckpointCapability | str = CheckpointCapability.NONE,
        checkpoint_ref: str = "",
        shutdown_policy: ShutdownPolicy | str = ShutdownPolicy.CANCEL,
        partial_result_policy: PartialResultPolicy | str = PartialResultPolicy.KEEP,
        operation_id: str = "",
        manifest_ref: str = "",
    ) -> str:
        ids, names = tuple(source_ids), tuple(source_names)
        if (
            not kind.strip()
            or not action.strip()
            or len(ids) > MAX_SOURCES
            or len(names) > MAX_SOURCES
            or len(backend_job_id) > 256
        ):
            raise ValueError("Invalid job request")
        with self._condition:
            if self._closed:
                raise ValueError("Job runtime is closed")
            self._sequence += 1
            now = time.time()
            job_id = "job-" + uuid.uuid4().hex[:12]
            initial_state = "retrying" if retry_of else "queued"
            record = _JobRecord(
                job_id,
                self._sequence,
                kind[:80],
                action[:160],
                initial_state,
                None,
                now,
                None,
                None,
                tuple(str(value)[:256] for value in ids),
                tuple(str(value)[:256] for value in names),
                backend_job_id,
                "再試行中" if retry_of else "待機中",
                "",
                CancelCapability(cancel_capability) is not CancelCapability.NONE,
                bool(retryable),
                str(retry_of)[:80],
                CancelCapability(cancel_capability).value,
                CheckpointCapability(checkpoint_capability).value,
                str(checkpoint_ref)[:512],
                ShutdownPolicy(shutdown_policy).value,
                PartialResultPolicy(partial_result_policy).value,
                str(operation_id)[:128],
                str(manifest_ref)[:512],
            )
            record.logs.append("retrying" if retry_of else "queued")
            self._records[job_id] = record
            self._cancel[job_id] = cancel_event or Event()
            self._queue.append(job_id)
            self._trim_locked()
            self._condition.notify_all()
            self._persist_locked()
            return job_id

    # {
    #   責務: [prepare: queued Jobをpreparing状態へ遷移させる]
    #   処理: [1: Job stateを検証する 2: preparingへ遷移してsnapshotを保存する]
    #   引数: [job_id: 準備開始するJob ID]
    #   戻り値: [prepared: state transitionを受理したか]
    # }
    def prepare(self, job_id: str) -> bool:
        with self._condition:
            record = self._records.get(job_id)
            if record is None or record.state != "queued":
                return False
            record.state = "preparing"
            record.message = "実行準備中"
            record.logs.append("preparing")
            self._persist_locked()
            return True

    # {
    #   責務: [wait_start: FIFO queueでbounded execution slotを待つ]
    #   処理: [1: cancel/closeを確認する 2: queue先頭かつslot availableならrunningへ遷移する]
    #   引数: [job_id: 開始するJob ID]
    #   戻り値: [started: workerがslotを取得したか]
    # }
    def wait_start(self, job_id: str) -> bool:
        with self._condition:
            while True:
                record = self._records.get(job_id)
                cancel = self._cancel.get(job_id)
                if record is None or cancel is None:
                    return False
                self._attached_workers.add(job_id)
                if record.state in TERMINAL_JOB_STATES:
                    self._attached_workers.discard(job_id)
                    return False
                if self._closed or cancel.is_set():
                    self._finish_locked(record, "cancelled", "開始前にキャンセルしました", "")
                    self._attached_workers.discard(job_id)
                    return False
                if (
                    record.state in {"queued", "preparing", "retrying"}
                    and self._queue
                    and self._queue[0] == job_id
                    and len(self._running) < self.max_concurrent
                ):
                    if self._resource_manager is not None:
                        lease = self._resource_manager.try_acquire(
                            self._resource_application_id,
                            job_id,
                            self._resource_kind,
                            self._resource_units,
                        )
                        if lease is None:
                            self._condition.wait(0.05)
                            continue
                        self._resource_leases[job_id] = lease
                    self._queue.popleft()
                    self._running.add(job_id)
                    record.state = "running"
                    record.started_at = time.time()
                    record.message = "実行中"
                    record.logs.append("running")
                    self._condition.notify_all()
                    self._persist_locked()
                    return True
                self._condition.wait(0.05)

    # {
    #   責務: [update: Job progress/message/logを更新する]
    #   処理: [1: progressを検証する 2: nonterminal recordを更新してpersistする]
    #   引数: [job_id: 対象Job, progress: 0..1またはNone, message: 表示message, log: compact log行]
    #   戻り値: []
    # }
    def update(
        self, job_id: str, progress: float | None = None, message: str = "", log: str = ""
    ) -> None:
        if progress is not None and (not math.isfinite(progress) or not 0 <= progress <= 1):
            raise ValueError("progress must be None or a finite value in 0..1")
        with self._condition:
            record = self._records.get(job_id)
            if record is None or record.state in TERMINAL_JOB_STATES:
                return
            if progress is not None:
                record.progress = progress
            if message:
                record.message = str(message)[:300]
            if log:
                record.logs.append(str(log)[:MAX_LOG_CHARS])
            self._persist_locked()

    # {
    #   責務: [set_backend_job_id: 外部backendのJob IDをsnapshotへ設定する]
    #   処理: [1: 外部ID長を検証する 2: Job recordとdurable snapshotを更新する]
    #   引数: [job_id: 対象Job, backend_job_id: backend側job/prompt ID]
    #   戻り値: []
    # }
    def set_backend_job_id(self, job_id: str, backend_job_id: str) -> None:
        if len(backend_job_id) > 256:
            raise ValueError("backend_job_id is too long")
        with self._condition:
            record = self._records.get(job_id)
            if record is None:
                raise KeyError(job_id)
            record.backend_job_id = backend_job_id
            self._persist_locked()

    # {
    #   責務: [finish: Jobをterminal stateへ遷移させる]
    #   処理: [1: terminal stateを検証する 2: slot/queueを解放して終端情報をpersistする]
    #   引数: [job_id: 対象Job, state: terminal state, message: 結果表示, error: error detail]
    #   戻り値: []
    # }
    def finish(self, job_id: str, state: str, message: str = "", error: str = "") -> None:
        if state not in TERMINAL_JOB_STATES:
            raise ValueError("terminal state required")
        with self._condition:
            record = self._records.get(job_id)
            if record is None or record.state in TERMINAL_JOB_STATES:
                return
            self._finish_locked(record, state, message, error)
            self._trim_locked()
            self._condition.notify_all()
            self._persist_locked()

    # {
    #   責務: [cancel: local cancel Eventと登録済みbackend停止要求を通知する]
    #   処理: [1: local停止を通知する 2: queue上のJobを終端化する 3: backend callbackを呼ぶ]
    #   引数: [job_id: 停止するJob ID]
    #   戻り値: [requested: 停止要求を受理したか]
    # }
    def cancel(self, job_id: str) -> bool:
        backend_handler = None
        backend_job_id = ""
        with self._condition:
            record = self._records.get(job_id)
            cancel = self._cancel.get(job_id)
            if (
                record is None
                or cancel is None
                or record.state in TERMINAL_JOB_STATES
                or not record.cancellable
            ):
                return False
            if job_id in self._cancel_requested:
                return False
            self._cancel_requested.add(job_id)
            cancel.set()
            backend_handler = self._backend_cancel_handlers.get(job_id)
            backend_job_id = record.backend_job_id
            if record.state in {"queued", "preparing", "retrying", "paused"}:
                self._finish_locked(record, "cancelled", "待機中にキャンセルしました", "")
            else:
                record.state = "cancelling"
                record.message = "停止要求済み — 現在のIO完了/timeoutを待っています"
                record.logs.append("cancel requested")
            self._condition.notify_all()
            self._persist_locked()
        self._dispatch_backend_cancel(job_id, backend_handler, backend_job_id)
        return True

    # {
    #   責務: [snapshots: immutable newest-first Job snapshot tupleを返す]
    #   処理: [1: condition lockを取得する 2: mutable recordをimmutable contractへ変換する]
    #   引数: []
    #   戻り値: [snapshots: 現在のJob history]
    # }
    def snapshots(self) -> tuple[JobSnapshot, ...]:
        with self._condition:
            return self._snapshots_locked()

    # {
    #   責務: [close: queued Jobをcancelし、running Jobへ停止要求してruntimeを閉じる]
    #   処理: [1: 新規Jobを拒否する 2: local cancelを通知する 3: backend停止要求をdispatchする]
    #   引数: []
    #   戻り値: []
    #   補足: [workerやbackendの完了を待たない]
    # }
    def close(self) -> None:
        backend_cancellations = []
        with self._condition:
            if self._closed:
                return
            self._closed = True
            for record in tuple(self._records.values()):
                if record.state not in ACTIVE_JOB_STATES:
                    continue
                if record.shutdown_policy == ShutdownPolicy.DETACH.value:
                    record.message = "GUI終了後もJobを継続します"
                    record.logs.append("detached on shutdown")
                    continue
                if (
                    record.shutdown_policy == ShutdownPolicy.FINISH_CURRENT_ITEM.value
                    and record.checkpoint_capability != CheckpointCapability.NONE.value
                ):
                    if record.state in {"queued", "preparing", "retrying"}:
                        self._finish_locked(record, "cancelled", "開始前に終了しました", "")
                        continue
                    self._finish_after_item.add(record.id)
                    record.state = "cancelling"
                    record.message = "現在のitem完了後に停止します"
                    record.logs.append("finish current item on shutdown")
                    continue
                if record.shutdown_policy == ShutdownPolicy.CHECKPOINT_AND_STOP.value:
                    if record.checkpoint_capability != CheckpointCapability.NONE.value:
                        if record.state in {"queued", "preparing", "retrying"}:
                            self._finish_locked(record, "cancelled", "開始前に終了しました", "")
                            continue
                        record.state = "pausing"
                        record.message = "終了時checkpointを要求しました"
                        record.logs.append("shutdown checkpoint requested")
                        continue
                cancel = self._cancel.get(record.id)
                cancellation_already_requested = record.id in self._cancel_requested
                if cancel is not None:
                    self._cancel_requested.add(record.id)
                    cancel.set()
                if record.state in {"queued", "preparing", "retrying", "paused"}:
                    self._finish_locked(record, "cancelled", "GUI終了によりキャンセルしました", "")
                else:
                    record.state = "cancelling"
                    record.message = "GUI終了による停止要求済み"
                    record.logs.append("shutdown cancel requested")
                    handler = self._backend_cancel_handlers.get(record.id)
                    if (
                        handler is not None
                        and record.backend_job_id
                        and not cancellation_already_requested
                    ):
                        backend_cancellations.append((record.id, handler, record.backend_job_id))
            self._condition.notify_all()
            self._persist_locked()
        for job_id, handler, backend_job_id in backend_cancellations:
            self._dispatch_backend_cancel(job_id, handler, backend_job_id)

    # {
    #   責務: [_dispatch_backend_cancel: backend停止callbackの失敗をJob logへ記録する]
    #   処理: [1: callbackがあれば呼ぶ 2: 例外種別をbounded logへ記録する]
    #   引数: [job_id: 対象Job, handler: backend停止callback, backend_job_id: 外部backend ID]
    #   戻り値: []
    #   補足: [handlerは非blockingで停止要求をenqueueすること]
    # }
    def _dispatch_backend_cancel(
        self,
        job_id: str,
        handler: CancelHandler | None,
        backend_job_id: str,
    ) -> None:
        if handler is None or not backend_job_id:
            return
        try:
            handler(backend_job_id)
        except Exception as exc:
            with self._condition:
                current = self._records.get(job_id)
                if current is not None:
                    current.logs.append(
                        f"backend cancel request failed: {type(exc).__name__}"[:MAX_LOG_CHARS]
                    )
                    self._persist_locked()

    # {
    #   責務: [_finish_locked: lock保持中にJob slotを解放してterminal recordへ変換する]
    #   処理: [1: running/queue/worker attachmentを解放する 2: terminal fields/logを更新する 3: snapshotを保存する]
    #   引数: [record: 対象record, state: terminal state, message: 表示結果, error: error detail]
    #   戻り値: []
    # }
    def _finish_locked(self, record: _JobRecord, state: str, message: str, error: str) -> None:
        if record.id in self._running:
            self._running.remove(record.id)
        self._attached_workers.discard(record.id)
        self._finish_after_item.discard(record.id)
        self._cancel_requested.discard(record.id)
        self._remove_from_queue_locked(record.id)
        self._release_resource_lease_locked(record.id)
        record.state = state
        record.finished_at = time.time()
        if state == "done":
            record.progress = 1.0
        record.message = str(message)[:300] or state
        record.error = str(error)[:500]
        record.logs.append((record.error or record.message)[:MAX_LOG_CHARS])
        self._persist_locked()

    # {
    #   責務: [_release_resource_lease_locked: job終了時にshared resource slotを解放する]
    #   処理: [1: job IDのleaseを取り除く 2: idempotent releaseを呼ぶ]
    #   引数: [job_id: 対象Job]
    #   戻り値: []
    # }
    def _release_resource_lease_locked(self, job_id: str) -> None:
        lease = self._resource_leases.pop(job_id, None)
        if lease is not None:
            lease.release()

    # {
    #   責務: [_try_acquire_resource_lease_locked: pause後の再開用resource slotをnonblocking取得する]
    #   処理: [1: unmanaged runtimeを許容する 2: shared leaseが取れた場合のみ保存する]
    #   引数: [job_id: 対象Job]
    #   戻り値: [acquired: lease取得結果]
    # }
    def _try_acquire_resource_lease_locked(self, job_id: str) -> bool:
        if self._resource_manager is None:
            return True
        lease = self._resource_manager.try_acquire(
            self._resource_application_id,
            job_id,
            self._resource_kind,
            self._resource_units,
        )
        if lease is None:
            return False
        self._resource_leases[job_id] = lease
        return True

    # {
    #   責務: [_remove_from_queue_locked: queueからJob IDを安全に除去する]
    #   処理: [1: queue内の対象を削除する 2: 未登録なら何もしない]
    #   引数: [job_id: queueから削除するJob]
    #   戻り値: []
    # }
    def _remove_from_queue_locked(self, job_id: str) -> None:
        try:
            self._queue.remove(job_id)
        except ValueError:
            pass

    # {
    #   責務: [_trim_locked: history上限を超えたとき古いterminal recordを削除する]
    #   処理: [1: terminal recordsを古い順に並べる 2: 上限内までruntime mapから削除する]
    #   引数: []
    #   戻り値: []
    # }
    def _trim_locked(self) -> None:
        if len(self._records) <= self.history_limit:
            return
        terminal = sorted(
            (record for record in self._records.values() if record.state in TERMINAL_JOB_STATES),
            key=lambda item: (item.created_at, item.sequence),
        )
        for record in terminal:
            if len(self._records) <= self.history_limit:
                break
            self._records.pop(record.id, None)
            self._cancel.pop(record.id, None)
            self._backend_cancel_handlers.pop(record.id, None)
