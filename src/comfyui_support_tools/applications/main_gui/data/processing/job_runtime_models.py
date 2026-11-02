"""Private bounded Job state records shared by runtime control modules."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from comfyui_support_tools.shared.contracts.job_contracts import (
    CancelCapability,
    CheckpointCapability,
    JobSnapshot,
    PartialResultPolicy,
    ShutdownPolicy,
)

MAX_LOG_LINES = 50
MAX_LOG_CHARS = 400
MAX_SOURCES = 100

CancelHandler = Callable[[str], None]
ResumeHandler = Callable[[JobSnapshot], None]
RetryHandler = Callable[[JobSnapshot], str]


# {
#   責務: [_JobRecord: durable共有Job snapshotを更新するmutable内部record]
#   フィールド: [lifecycle、capability、manifest/checkpoint、item/artifact参照、bounded log]
# }
@dataclass
class _JobRecord:
    id: str
    sequence: int
    kind: str
    action: str
    state: str
    progress: float | None
    created_at: float
    started_at: float | None
    finished_at: float | None
    source_ids: tuple[str, ...]
    source_names: tuple[str, ...]
    backend_job_id: str
    message: str
    error: str
    cancellable: bool
    retryable: bool
    retry_of: str
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
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
