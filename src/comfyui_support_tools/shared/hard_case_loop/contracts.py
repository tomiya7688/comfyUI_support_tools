"""Versioned local contracts for Touka real-input hard-case feedback."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


# {
#   責務: [CandidateEvidence: one generated candidate's raw score and confidenceを表す]
#   フィールド: [candidate_id, score, confidence]
# }
@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    candidate_id: str
    score: float
    confidence: float

    # {
    #   責務: [__post_init__: candidate evidence値をvalidateする]
    #   処理: [require normalized finite score/confidence and stable candidate identity]
    #   引数: [self: immutable candidate metrics]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must not be empty")
        _normalized(self.score, "score")
        _normalized(self.confidence, "confidence")


# {
#   責務: [HardCaseFeatures: hardnessを複数軸のnormalized featureで保持する]
#   フィールド: [reconstruction_residual, low_confidence_area_ratio, candidate_disagreement, temporal_disagreement, artifact_score]
# }
@dataclass(frozen=True, slots=True)
class HardCaseFeatures:
    reconstruction_residual: float = 0.0
    low_confidence_area_ratio: float = 0.0
    candidate_disagreement: float = 0.0
    temporal_disagreement: float = 0.0
    artifact_score: float = 0.0

    # {
    #   責務: [__post_init__: hardness featureをnormalized範囲へ制限する]
    #   処理: [reject NaN, infinity and non-normalized values]
    #   引数: [self: feature vector]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            _normalized(value, name)


# {
#   責務: [HardCaseRecord: local failure loopに必要なmetadataとuser feedbackを保持する]
#   フィールド: [identity, provenance, candidates, feedback, regression membership, runtime/model metadata]
#   処理: [preserve only references and metrics; never embed image bytes]
# }
@dataclass(frozen=True, slots=True)
class HardCaseRecord:
    record_id: str
    dataset_id: str
    input_sha256: str
    media_type: str
    local_path_reference: str
    candidates: tuple[CandidateEvidence, ...]
    features: HardCaseFeatures
    failure_tags: tuple[str, ...] = ()
    material: str = "unknown"
    estimated_conditions: tuple[str, ...] = ()
    confidence_map_references: tuple[str, ...] = ()
    selected_candidate: str = ""
    user_preferred_candidate: str = ""
    rejected_candidates: tuple[str, ...] = ()
    feedback_received: bool = False
    runtime_seconds: float = 0.0
    peak_vram_mib: float = 0.0
    model_version: str = "unknown"
    config_fingerprint: str = "unknown"
    ground_truth_reference: str = ""
    weak_labels: tuple[str, ...] = ()
    in_regression_set: bool = False
    metadata: tuple[tuple[str, str], ...] = ()
    schema: str = "touka-hard-case.v1"

    # {
    #   責務: [__post_init__: failure record identity, privacy references, metrics and feedbackを検証する]
    #   処理: [require local path references and candidate IDs to remain internally consistent]
    #   引数: [self: immutable hard-case record]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if self.schema != "touka-hard-case.v1":
            raise ValueError("unsupported hard-case record schema")
        if not self.record_id.strip() or not self.dataset_id.strip():
            raise ValueError("hard-case record requires record and dataset IDs")
        if len(self.input_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.input_sha256
        ):
            raise ValueError("input_sha256 must be a lowercase SHA-256 digest")
        if self.media_type not in {"image", "video", "burst", "frame_sequence"}:
            raise ValueError("unsupported hard-case media type")
        if not self.local_path_reference:
            raise ValueError("hard-case record requires a local path reference")
        if self.local_path_reference.lower().startswith(("http://", "https://")):
            raise ValueError("hard-case path references must remain local")
        if not self.candidates or len(
            {candidate.candidate_id for candidate in self.candidates}
        ) != len(self.candidates):
            raise ValueError("hard-case record requires uniquely identified candidates")
        candidate_ids = {candidate.candidate_id for candidate in self.candidates}
        if self.selected_candidate and self.selected_candidate not in candidate_ids:
            raise ValueError("selected candidate is absent from the candidate list")
        if self.user_preferred_candidate and self.user_preferred_candidate not in candidate_ids:
            raise ValueError("preferred candidate is absent from the candidate list")
        if not set(self.rejected_candidates).issubset(candidate_ids):
            raise ValueError("rejected candidate is absent from the candidate list")
        if len(self.rejected_candidates) != len(set(self.rejected_candidates)):
            raise ValueError("rejected candidate IDs must be unique")
        if self.user_preferred_candidate in self.rejected_candidates:
            raise ValueError("user-preferred candidate cannot also be rejected")
        if not isinstance(self.feedback_received, bool) or not isinstance(
            self.in_regression_set, bool
        ):
            raise ValueError("feedback and regression membership flags must be boolean")
        if self.feedback_received and not (
            self.user_preferred_candidate or self.rejected_candidates
        ):
            raise ValueError("feedback_received requires a preference or rejected candidate")
        for name, value in (
            ("runtime_seconds", self.runtime_seconds),
            ("peak_vram_mib", self.peak_vram_mib),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        if len(dict(self.metadata)) != len(self.metadata):
            raise ValueError("metadata keys must be unique")
        if any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in self.metadata
        ):
            raise ValueError("metadata keys and values must be strings")

    # {
    #   責務: [to_document: nested dataclassをversioned JSON-compatible dictへ変換する]
    #   処理: [serialize only metadata, references, hashes, scores and feedback]
    #   引数: [self: hard-case record]
    #   戻り値: [dict[str, Any]: portable local manifest entry]
    # }
    def to_document(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "features": asdict(self.features),
            "candidates": [asdict(candidate) for candidate in self.candidates],
        }

    # {
    #   責務: [from_document: persisted JSON-compatible dictをvalidated recordへ復元する]
    #   処理: [construct typed child values before validating the complete contract]
    #   引数: [value: decoded local JSON object]
    #   戻り値: [HardCaseRecord: validated hard-case data]
    # }
    @classmethod
    def from_document(cls, value: dict[str, Any]) -> HardCaseRecord:
        if not isinstance(value, dict):
            raise ValueError("hard-case record must be a JSON object")
        document = dict(value)
        document["features"] = HardCaseFeatures(**document["features"])
        document["candidates"] = tuple(CandidateEvidence(**item) for item in document["candidates"])
        for key in (
            "failure_tags",
            "estimated_conditions",
            "confidence_map_references",
            "rejected_candidates",
            "weak_labels",
        ):
            document[key] = tuple(document.get(key, ()))
        document["metadata"] = tuple(tuple(row) for row in document.get("metadata", ()))
        return cls(**document)


# {
#   責務: [_normalized: confidence-like scalarをfinite 0..1へvalidateする]
#   処理: [reject bool, non-number, NaN and out-of-range input]
#   引数: [value: scalar, name: field name]
#   戻り値: []
# }
def _normalized(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"{name} must be finite and between zero and one")
