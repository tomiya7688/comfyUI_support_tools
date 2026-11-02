"""Cross-application durable run manifest and provenance contracts."""

from dataclasses import dataclass
from enum import Enum


# {
#   責務: [RunStatus: run manifestのlifecycle状態を定義する]
#   フィールド: [running/succeeded/failed/cancelled/interrupted]
# }
class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


# {
#   責務: [ReproducibilityLevel: replay fidelityを過大表示せず分類する]
#   フィールド: [deterministic/best_effort/non_deterministic]
# }
class ReproducibilityLevel(str, Enum):
    DETERMINISTIC = "deterministic"
    BEST_EFFORT = "best_effort"
    NON_DETERMINISTIC = "non_deterministic"


# {
#   責務: [PrivacyMode: manifest fieldの保存形式を指定する]
#   フィールド: [full/hash/summary/none]
# }
class PrivacyMode(str, Enum):
    FULL = "full"
    HASH = "hash"
    SUMMARY = "summary"
    NONE = "none"


# {
#   責務: [ArtifactReference: input/outputを埋め込まずURIとfingerprintで参照する]
#   フィールド: [artifact ID、URI、size/hash、media timing metadata]
# }
@dataclass(frozen=True)
class ArtifactReference:
    artifact_id: str
    uri: str
    size_bytes: int | None = None
    sha256: str = ""
    media_timing: tuple[tuple[str, object], ...] = ()
    media_type: str = ""


# {
#   責務: [ComponentVersion: backend/model/tool/adapter versionを追跡する]
#   フィールド: [component ID、version、optional artifact/model reference]
# }
@dataclass(frozen=True)
class ComponentVersion:
    component_id: str
    version: str
    reference: str = ""


# {
#   責務: [RunDecision: selected/rejected/repair decisionsを説明する]
#   フィールド: [decision ID/category/outcome/reason/candidate/score/details]
# }
@dataclass(frozen=True)
class RunDecision:
    decision_id: str
    category: str
    outcome: str
    reason: str = ""
    candidate_ref: str = ""
    score: float | None = None
    details: tuple[tuple[str, object], ...] = ()


# {
#   責務: [RunLineage: parent/child/retry/repairのprovenanceを記録する]
#   フィールド: [parent run、children、retry source、repair source、label]
# }
@dataclass(frozen=True)
class RunLineage:
    parent_run_id: str = ""
    child_run_ids: tuple[str, ...] = ()
    retry_of_run_id: str = ""
    repair_of_run_id: str = ""
    relation: str = ""


# {
#   責務: [RunManifest: cross-application execution recordのversioned immutable schema]
#   フィールド: [identity/lifecycle/inputs/settings/seeds/versions/environment/outputs/decisions/privacy/provenance]
# }
@dataclass(frozen=True)
class RunManifest:
    run_id: str
    application_id: str
    application_version: str
    settings_schema_version: str
    started_at: float
    finished_at: float | None
    status: RunStatus
    reproducibility: ReproducibilityLevel
    input_refs: tuple[ArtifactReference, ...]
    resolved_settings: tuple[tuple[str, object], ...]
    random_seeds: tuple[tuple[str, int], ...]
    random_selections: tuple[tuple[str, object], ...]
    component_versions: tuple[ComponentVersion, ...]
    environment: tuple[tuple[str, object], ...]
    output_artifacts: tuple[ArtifactReference, ...]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    decisions: tuple[RunDecision, ...]
    selected_candidate_refs: tuple[str, ...]
    rejected_candidate_refs: tuple[str, ...]
    repair_history: tuple[RunDecision, ...]
    user_overrides: tuple[tuple[str, object], ...]
    lineage: RunLineage
    provenance: tuple[tuple[str, object], ...]
    privacy_modes: tuple[tuple[str, PrivacyMode], ...]
    schema_version: int = 1


# {
#   責務: [RunManifestEvent: JSONL event storeで順序付きlifecycle更新を表す]
#   フィールド: [run ID、sequence、timestamp、event type、privacy-filtered payload]
# }
@dataclass(frozen=True)
class RunManifestEvent:
    run_id: str
    sequence: int
    created_at: float
    event_type: str
    payload: tuple[tuple[str, object], ...] = ()


# {
#   責務: [RunReplayRequest: manifestから同一設定/seed再投入用のrequestを表す]
#   フィールド: [application、input refs、resolved settings、seeds、reproducibility level]
# }
@dataclass(frozen=True)
class RunReplayRequest:
    application_id: str
    input_refs: tuple[ArtifactReference, ...]
    resolved_settings: tuple[tuple[str, object], ...]
    random_seeds: tuple[tuple[str, int], ...]
    reproducibility: ReproducibilityLevel
    source_run_id: str


# {
#   責務: [ManifestDifference: run間のpath別差分を追跡可能にする]
#   フィールド: [field path、left value、right value]
# }
@dataclass(frozen=True)
class ManifestDifference:
    field_path: str
    left_value: object
    right_value: object
