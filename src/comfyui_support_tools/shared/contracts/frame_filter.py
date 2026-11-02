"""Serializable contracts for low-information frame analysis and review."""

from dataclasses import dataclass
from enum import Enum


# {
#   責務: [FrameFilterDecision: feature evidenceから解決したframe policyを定義する]
#   フィールド: [keep、drop、review、error]
# }
class FrameFilterDecision(str, Enum):
    KEEP = "keep"
    DROP = "drop"
    REVIEW = "review"
    ERROR = "error"


# {
#   責務: [FrameFilterAction: low-information frameへの保存時動作を定義する]
#   フィールド: [drop、move rejected、review queue、mark only]
# }
class FrameFilterAction(str, Enum):
    DROP = "drop"
    MOVE_TO_REJECTED = "move_to_rejected"
    REVIEW_QUEUE = "review_queue"
    MARK_ONLY = "mark_only"


# {
#   責務: [FrameFilterPreset: filter強度のversion付き選択肢を定義する]
#   フィールド: [conservative、balanced、aggressive、custom]
# }
class FrameFilterPreset(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


# {
#   責務: [FrameTextBox: optional OCR analyzerのnormalized text位置を保持する]
#   フィールド: [normalized bounding box、confidence、text line group]
# }
@dataclass(frozen=True)
class FrameTextBox:
    x: float
    y: float
    width: float
    height: float
    confidence: float = 1.0
    text: str = ""


# {
#   責務: [ReviewDecision: GUI/userがreview itemへ適用する選択を定義する]
#   フィールド: [keep、drop、separate]
# }
class ReviewDecision(str, Enum):
    KEEP = "keep"
    DROP = "drop"
    SEPARATE = "separate"


# {
#   責務: [FrameFilterOptions: per-run filterのenable/preset/rules/actionsを保持する]
#   フィールド: [enable、analysis mode、rule switches、title/credits policy、confidence band]
# }
@dataclass(frozen=True)
class FrameFilterOptions:
    enabled: bool = False
    preset: FrameFilterPreset = FrameFilterPreset.CONSERVATIVE
    action: FrameFilterAction = FrameFilterAction.REVIEW_QUEUE
    purpose: str = "dataset"
    detect_black: bool = True
    detect_white: bool = True
    detect_transition: bool = True
    detect_text_only: bool = True
    detect_title_credits: bool = True
    detect_low_detail: bool = True
    detect_blur: bool = True
    compare_neighbors: bool = True
    title_credits_policy: str = "keep"
    low_confidence_threshold: float = 0.55
    high_confidence_threshold: float = 0.88
    custom_extreme_ratio_threshold: float = 0.995
    custom_candidate_threshold: float = 0.86
    custom_title_threshold: float = 0.9
    custom_information_protection_threshold: float = 0.08
    analyzer_version: str = "frame-filter-1"


# {
#   責務: [FrameFilterReport: frame別features/evidence/decisionとlineageを保存する]
#   フィールド: [timestamp、luminance/detail/text/subject/temporal metrics、decision/reason/provenance]
# }
@dataclass(frozen=True)
class FrameFilterReport:
    frame_index: int
    timestamp: float | None
    mean_luminance: float | None
    black_ratio: float | None
    white_ratio: float | None
    entropy: float | None
    edge_density: float | None
    sharpness: float | None
    text_area_ratio: float | None
    non_text_information_score: float | None
    subject_score: float | None
    saliency_score: float | None
    neighbor_similarity: float | None
    transition_score: float | None
    title_card_score: float | None
    credits_score: float | None
    low_information_score: float
    decision: FrameFilterDecision
    reasons: tuple[str, ...]
    confidence: float
    provenance: tuple[tuple[str, str], ...]


# {
#   責務: [FrameFilterBatchManifest: batch-level filter summaryを保存する]
#   フィールド: [source、options、reports、counts、created timestamp]
# }
@dataclass(frozen=True)
class FrameFilterBatchManifest:
    source_id: str
    options: FrameFilterOptions
    reports: tuple[FrameFilterReport, ...]
    kept_count: int
    dropped_count: int
    review_count: int
    error_count: int
