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

    # {
    #   責務: [to_dict: sampling planとattempt lineageをJSON-compatible mappingへ変換する]
    #   処理: [1: enumとoptionsをserializeする 2: Fractionをnumerator/denominatorへ変換する]
    #   引数: [self: result]
    #   戻り値: [payload: manifest保存用mapping]
    # }
    def to_dict(self) -> dict[str, object]:
        # {
        #   責務: [record_dict: frame attempt lineageをJSON値へ変換する]
        #   処理: [1: sample metadataをmappingへ写す 2: time_baseを整数pairへ変換する]
        #   引数: [record: attempt record]
        #   戻り値: [record payload]
        # }
        def record_dict(record: FrameSampleRecord) -> dict[str, object]:
            time_base = record.time_base
            return {
                "candidate_id": record.candidate_id,
                "source_video_id": record.source_video_id,
                "requested_timestamp": record.requested_timestamp,
                "actual_timestamp": record.actual_timestamp,
                "pts": record.pts,
                "time_base": None
                if time_base is None
                else {"numerator": time_base.numerator, "denominator": time_base.denominator},
                "bin_id": record.bin_id,
                "sample_generation": record.sample_generation,
                "filter_result": record.filter_result,
                "parent_candidate_id": record.parent_candidate_id,
            }

        return {
            "schema_version": 1,
            "source_video_id": self.source_video_id,
            "duration": self.duration,
            "count_mode": self.count_mode.value,
            "requested_count": self.requested_count,
            "sampling_seed": self.sampling_seed,
            "options": {
                "count_mode": self.options.count_mode.value,
                "sampling_seed": self.options.sampling_seed,
                "bin_count": self.options.bin_count,
                "max_attempts": self.options.max_attempts,
                "max_candidate_multiplier": self.options.max_candidate_multiplier,
                "max_wall_time_seconds": self.options.max_wall_time_seconds,
            },
            "bins": [{"id": item.id, "start": item.start, "end": item.end} for item in self.bins],
            "attempts": [record_dict(item) for item in self.attempts],
            "kept": [record_dict(item) for item in self.kept],
            "exhausted_reason": self.exhausted_reason,
        }
