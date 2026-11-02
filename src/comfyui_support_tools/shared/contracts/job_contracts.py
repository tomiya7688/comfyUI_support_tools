"""GUI-independent job snapshots shared by present and future backends."""

from dataclasses import dataclass
from enum import Enum


# {
#   責務: [JobState: 共通Job lifecycleの状態を定義する]
#   フィールド: [queuedからterminal stateまでのstate名]
# }
class JobState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    RESUMING = "resuming"
    RETRYING = "retrying"
    DONE = "done"
    FAILED = "failed"
    ERROR = "error"  # Backward-compatible alias used by existing adapters.
    INTERRUPTED = "interrupted"


# {
#   責務: [CancelCapability: backend停止方式を宣言する]
#   フィールド: [cooperative、process、backend、none]
# }
class CancelCapability(str, Enum):
    COOPERATIVE = "cooperative"
    PROCESS = "process"
    BACKEND = "backend"
    NONE = "none"


# {
#   責務: [CheckpointCapability: 再開可能なcheckpoint粒度を宣言する]
#   フィールド: [none、stage、item、native]
# }
class CheckpointCapability(str, Enum):
    NONE = "none"
    STAGE = "stage"
    ITEM = "item"
    NATIVE = "native"


# {
#   責務: [ShutdownPolicy: application shutdown時のJob処理を指定する]
#   フィールド: [cancel、finish_current_item、checkpoint_and_stop、detach]
# }
class ShutdownPolicy(str, Enum):
    CANCEL = "cancel"
    FINISH_CURRENT_ITEM = "finish_current_item"
    CHECKPOINT_AND_STOP = "checkpoint_and_stop"
    DETACH = "detach"


# {
#   責務: [PartialResultPolicy: 部分成果物の失敗時処理を指定する]
#   フィールド: [keep、quarantine、rollback]
# }
class PartialResultPolicy(str, Enum):
    KEEP = "keep"
    QUARANTINE = "quarantine"
    ROLLBACK = "rollback"


TERMINAL_JOB_STATES = frozenset({"done", "error", "failed", "cancelled", "interrupted"})
ACTIVE_JOB_STATES = frozenset(
    {"queued", "preparing", "running", "pausing", "paused", "cancelling", "resuming", "retrying"}
)


# {
#   責務: [JobSnapshot: UI、CLI、Application間のimmutable Job contractを表す]
#   フィールド: [lifecycle、capability、checkpoint、manifest、item/artifact状態]
# }
@dataclass(frozen=True)
class JobSnapshot:
    id: str
    kind: str
    action: str
    state: str
    progress: float | None
    created_at: float
    started_at: float | None
    finished_at: float | None
    source_ids: tuple[str, ...] = ()
    source_names: tuple[str, ...] = ()
    backend_job_id: str = ""
    message: str = ""
    error: str = ""
    logs: tuple[str, ...] = ()
    cancellable: bool = True
    retryable: bool = False
    retry_of: str = ""
    cancel_capability: str = CancelCapability.COOPERATIVE.value
    checkpoint_capability: str = CheckpointCapability.NONE.value
    checkpoint_ref: str = ""
    shutdown_policy: str = ShutdownPolicy.CANCEL.value
    partial_result_policy: str = PartialResultPolicy.KEEP.value
    operation_id: str = ""
    manifest_ref: str = ""
    completed_items: tuple[str, ...] = ()
    pending_items: tuple[str, ...] = ()
    failed_items: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
