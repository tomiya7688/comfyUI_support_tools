"""Serializable sampling contracts for video frame selection and refill lineage."""

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from comfyui_support_tools.shared.contracts.frame_analysis import FrameAnalysisInput


# {
#   責務: [FrameCountMode: Movie Framesの指定枚数の意味を表す]
#   フィールド: [candidate_count、target_kept]
# }
class FrameCountMode(str, Enum):
    CANDIDATE_COUNT = "candidate_count"
    TARGET_KEPT = "target_kept"


# {
#   責務: [SamplingBin: 時間/scene/shot分布を保つ連続timestamp範囲を表す]
#   フィールド: [id、start、end]
# }
@dataclass(frozen=True)
class SamplingBin:
    id: str
    start: float
    end: float


# {
#   責務: [FrameSamplingOptions: deterministic bounded sampling policyを保持する]
#   フィールド: [count mode、seed、bin count、attempt/multiplier/time budget]
# }
@dataclass(frozen=True)
class FrameSamplingOptions:
    count_mode: FrameCountMode = FrameCountMode.TARGET_KEPT
    sampling_seed: int = 0
    bin_count: int = 10
    max_attempts: int = 1000
    max_candidate_multiplier: int = 4
    max_wall_time_seconds: float = 60.0


# {
#   責務: [FrameEvaluation: sampling candidateをdecode/filterした結果を表す]
#   フィールド: [normalized frame、filter keep判定、filter理由]
# }
@dataclass(frozen=True)
class FrameEvaluation:
    frame: FrameAnalysisInput | None
    keep: bool
    reason: str = ""


# {
#   責務: [FrameSampleRecord: initial/replacement candidateとfilter結果のmanifest lineageを表す]
#   フィールド: [source/time/PTS、bin、sample generation、filter result、parent candidate]
# }
@dataclass(frozen=True)
class FrameSampleRecord:
    candidate_id: str
    source_video_id: str
    requested_timestamp: float
    actual_timestamp: float | None
    pts: int | None
    time_base: Fraction | None
    bin_id: str
    sample_generation: str
    filter_result: str
    parent_candidate_id: str = ""


# {
#   責務: [FrameSamplingResult: deterministic sampling planと補充結果を保存する]
#   フィールド: [mode、seed、target、attempts、kept、exhausted reason]
# }
@dataclass(frozen=True)
class FrameSamplingResult:
    source_video_id: str
    duration: float
    count_mode: FrameCountMode
    requested_count: int
    sampling_seed: int
    options: FrameSamplingOptions
    bins: tuple[SamplingBin, ...]
    attempts: tuple[FrameSampleRecord, ...]
    kept: tuple[FrameSampleRecord, ...]
    exhausted_reason: str
