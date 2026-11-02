"""Shared GUI/CLI contract for safe plan, preview, and apply workflows."""

from dataclasses import dataclass
from enum import Enum


# {
#   責務: [OperationMode: mutation前の確認/実行モードを共通定義する]
#   フィールド: [analyze、dry_run、preview_sample、apply、apply_with_review、manifest_only]
# }
class OperationMode(str, Enum):
    ANALYZE_ONLY = "analyze_only"
    DRY_RUN = "dry_run"
    PREVIEW_SAMPLE = "preview_sample"
    APPLY = "apply"
    APPLY_WITH_REVIEW = "apply_with_review"
    MANIFEST_ONLY = "manifest_only"


# {
#   責務: [SourceSnapshot: OperationPlan作成時のsource fingerprintを保持する]
#   フィールド: [source ID/path、existence、stat identity、optional content digest]
# }
@dataclass(frozen=True)
class SourceSnapshot:
    source_id: str
    path: str
    exists: bool
    size_bytes: int
    modified_ns: int
    mode: int
    device_id: int
    inode: int
    content_sha256: str = ""


# {
#   責務: [PlannedAction: preview/apply対象の1つのproposed operationを表す]
#   フィールド: [source/action/destination、decision reason、risk/review、confidence/reversibility]
# }
@dataclass(frozen=True)
class PlannedAction:
    action_id: str
    source_id: str
    operation: str
    destination: str = ""
    decision_reasons: tuple[str, ...] = ()
    risk_level: str = "normal"
    review_required: bool = False
    reversible: bool = True
    confidence: float = 1.0


# {
#   責務: [OperationPlan: GUI/CLI共通のanalyze/preview/apply immutable planを保持する]
#   フィールド: [source/action列、affected counts、warning/conflict、resources/output、settings digest、revision]
# }
@dataclass(frozen=True)
class OperationPlan:
    operation_id: str
    mode: OperationMode
    source_items: tuple[SourceSnapshot, ...]
    proposed_actions: tuple[PlannedAction, ...]
    affected_count: int
    skipped_count: int
    before_count: int
    after_count: int
    warnings: tuple[str, ...]
    conflicts: tuple[str, ...]
    estimated_resources: tuple[tuple[str, int | float | str], ...]
    output_destinations: tuple[str, ...]
    decision_reasons: tuple[str, ...]
    reversible: bool
    confidence: float
    settings_sha256: str
    created_at: float
    schema_version: int = 1


# {
#   責務: [OperationPreview: representative/high-risk/random sampleを共通表示する]
#   フィールド: [action samples、risk/count metrics、reason distribution、before/after count]
# }
@dataclass(frozen=True)
class OperationPreview:
    actions: tuple[PlannedAction, ...]
    affected_count: int
    skipped_count: int
    review_count: int
    before_count: int
    after_count: int
    reason_distribution: tuple[tuple[str, int], ...]


# {
#   責務: [PlanExecutionStatus: stale/review/applyの結果を明示する]
#   フィールド: [applied、stale_source、stale_settings、stale_decisions、confirmation_required、manifest_only、failed]
# }
class PlanExecutionStatus(str, Enum):
    PLAN_READY = "plan_ready"
    APPLIED = "applied"
    BLOCKED_CONFLICT = "blocked_conflict"
    STALE_SOURCE = "stale_source"
    STALE_SETTINGS = "stale_settings"
    STALE_DECISIONS = "stale_decisions"
    CONFIRMATION_REQUIRED = "confirmation_required"
    MANIFEST_ONLY = "manifest_only"
    FAILED = "failed"


# {
#   責務: [PlanExecutionResult: apply時に実行された件数とblock理由を返す]
#   フィールド: [status、applied count、message]
# }
@dataclass(frozen=True)
class PlanExecutionResult:
    status: PlanExecutionStatus
    applied_count: int = 0
    message: str = ""
