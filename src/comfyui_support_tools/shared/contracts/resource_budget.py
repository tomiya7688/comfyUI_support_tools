"""Shared resource budget and stage execution contracts."""

import threading
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum


# {
#   責務: [ResourceKind: ResourceBudgetManagerが共有上限を管理するresource種類を定義する]
#   フィールド: [CPU thread/process、GPU、VRAM/RAM、disk、network、external API]
# }
class ResourceKind(str, Enum):
    CPU_THREADS = "cpu_threads"
    CPU_PROCESSES = "cpu_processes"
    GPU_JOBS = "gpu_jobs"
    VRAM_MB = "vram_budget_mb"
    RAM_MB = "ram_budget_mb"
    DISK_IO_JOBS = "disk_io_jobs"
    NETWORK_JOBS = "network_jobs"
    EXTERNAL_API = "external_api_concurrency"


# {
#   責務: [CancellationPolicy: stage cancellation後のactive item扱いを定義する]
#   フィールド: [pending破棄後の即時cancelまたはactive item完了]
# }
class CancellationPolicy(str, Enum):
    CANCEL_PENDING = "cancel_pending"
    FINISH_ACTIVE = "finish_active"


# {
#   責務: [ResourceBudget: resource種類別のconcrete safe limitsを保持する]
#   フィールド: [cpu/gpu/memory/disk/network/api/queue limits]
# }
@dataclass(frozen=True)
class ResourceBudget:
    cpu_threads: int = 4
    cpu_processes: int = 2
    gpu_jobs: int = 1
    vram_budget_mb: int | None = None
    ram_budget_mb: int | None = None
    disk_io_jobs: int = 2
    network_jobs: int = 4
    external_api_concurrency: int = 2
    queue_capacity: int = 8
    priority: int = 0
    cancellation_policy: CancellationPolicy = CancellationPolicy.CANCEL_PENDING


# {
#   責務: [ResourceBudgetOverride: global/application/run階層の部分設定を表す]
#   フィールド: [ResourceBudget各limitのoptional override]
# }
@dataclass(frozen=True)
class ResourceBudgetOverride:
    cpu_threads: int | None = None
    cpu_processes: int | None = None
    gpu_jobs: int | None = None
    vram_budget_mb: int | None = None
    ram_budget_mb: int | None = None
    disk_io_jobs: int | None = None
    network_jobs: int | None = None
    external_api_concurrency: int | None = None
    queue_capacity: int | None = None
    priority: int | None = None
    cancellation_policy: CancellationPolicy | str | None = None


# {
#   責務: [ResourceLease: resource reservationのcontext管理と解放を行う]
#   フィールド: [manager、scope、resource、units、release state]
# }
@dataclass
class ResourceLease:
    manager: object
    application_id: str
    run_id: str
    resource: ResourceKind
    units: int
    _released: bool = False
    _release_lock: threading.Lock = dataclass_field(default_factory=threading.Lock, repr=False)

    # {
    #   責務: [release: resource reservationを一度だけ返却する]
    #   処理: [1: 重複releaseを避ける 2: manager counterを減らす]
    #   引数: []
    #   戻り値: []
    # }
    def release(self) -> None:
        with self._release_lock:
            if not self._released:
                self.manager._release(self.application_id, self.run_id, self.resource, self.units)
                self._released = True

    # {
    #   責務: [__enter__: with blockを開始する]
    #   処理: [1: 自身を返す]
    #   引数: []
    #   戻り値: [lease: resource lease]
    # }
    def __enter__(self):
        return self

    # {
    #   責務: [__exit__: with block終了時にresourceを返却する]
    #   処理: [1: releaseを呼ぶ]
    #   引数: [exception_type/value/traceback: context manager exception情報]
    #   戻り値: [suppress: false]
    # }
    def __exit__(self, exception_type, exception_value, traceback) -> bool:
        self.release()
        return False


# {
#   責務: [ResourceStageMetrics: stage queue/処理のbounded observabilityを保持する]
#   フィールド: [submitted/completed/failed/cancelled/backpressure/OOM降格数]
# }
@dataclass(frozen=True)
class ResourceStageMetrics:
    submitted: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    backpressure_waits: int = 0
    degraded_after_oom: int = 0
