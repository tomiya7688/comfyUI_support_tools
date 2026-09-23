"""GUI-independent job snapshots shared by present and future backends."""
from dataclasses import dataclass

TERMINAL_JOB_STATES = frozenset({"done", "error", "cancelled"})
ACTIVE_JOB_STATES = frozenset({"queued", "running"})


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
