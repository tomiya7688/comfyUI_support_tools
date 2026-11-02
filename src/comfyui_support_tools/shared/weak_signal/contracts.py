"""Contracts for evidence-preserving weak-signal and layer-separation workflows."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


# {
#   責務: [WeakSignalMode: weak-signal image processing task priorsを列挙する]
#   フィールド: [AUTO, TRANSLUCENT_SURFACE, REFLECTION, GLARE, PAPER_SHOWTHROUGH, VEIL, WEAK_DETAIL, UNEVEN_ILLUMINATION]
# }
class WeakSignalMode(str, Enum):
    AUTO = "auto"
    TRANSLUCENT_SURFACE = "translucent_surface"
    REFLECTION = "reflection"
    GLARE = "glare"
    PAPER_SHOWTHROUGH = "paper_showthrough"
    VEIL = "veil"
    WEAK_DETAIL = "weak_detail"
    UNEVEN_ILLUMINATION = "uneven_illumination"


# {
#   責務: [EvidenceKind: candidate pixelsがinput observedかalgorithm inferredかを区別する]
#   フィールド: [OBSERVED, ENHANCED, INFERRED, COMPLETED]
# }
class EvidenceKind(str, Enum):
    OBSERVED = "observed"
    ENHANCED = "enhanced"
    INFERRED = "inferred"
    COMPLETED = "completed"


# {
#   責務: [ObservationInput: image/burst/video frameを同一input contractで受け取る]
#   フィールド: [observation_id, frames, media_kind, metadata]
# }
@dataclass(frozen=True, slots=True)
class ObservationInput:
    observation_id: str
    frames: tuple[bytes, ...]
    media_kind: str = "image"
    metadata: tuple[tuple[str, str], ...] = ()

    # {
    #   責務: [__post_init__: observation ID/frame payload/media kindをvalidateする]
    #   処理: [bound input frame count and retain encoded image bytes without altering evidence]
    #   引数: [self: immutable image, burst, or video-frame observation]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: invalid observation input]
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.observation_id, str) or not self.observation_id.strip():
            raise ValueError("observation_id must not be empty")
        if not isinstance(self.frames, tuple) or not self.frames or len(self.frames) > 512:
            raise ValueError("observation input must contain 1 to 512 immutable frames")
        if any(not isinstance(frame, bytes) or not frame for frame in self.frames):
            raise TypeError("observation frames must be non-empty encoded image bytes")
        if not isinstance(self.media_kind, str) or self.media_kind not in {
            "image",
            "burst",
            "video",
        }:
            raise ValueError("media_kind must be image, burst, or video")
        if self.media_kind == "image" and len(self.frames) != 1:
            raise ValueError("single-image observations must contain exactly one frame")


# {
#   責務: [WeakSignalRequest: selected/manual modeとintensity/candidate countを保持する]
#   フィールド: [mode, strength, candidate_count, alignment_assumed]
# }
@dataclass(frozen=True, slots=True)
class WeakSignalRequest:
    mode: WeakSignalMode = WeakSignalMode.AUTO
    strength: float = 0.5
    candidate_count: int = 3
    aligned_frames_assumed: bool = False

    # {
    #   責務: [__post_init__: mode, processing strength and candidate countをvalidateする]
    #   処理: [prevent unsupported ranges and reject unverified enum values]
    #   引数: [self: weak-signal processing preferences]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: malformed request]
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.mode, WeakSignalMode):
            raise TypeError("mode must use WeakSignalMode")
        if (
            isinstance(self.strength, bool)
            or not isinstance(self.strength, (float, int))
            or not math.isfinite(self.strength)
            or not 0 <= self.strength <= 1
        ):
            raise ValueError("strength must be finite and between zero and one")
        if (
            isinstance(self.candidate_count, bool)
            or not isinstance(self.candidate_count, int)
            or not 1 <= self.candidate_count <= 12
        ):
            raise ValueError("candidate_count must be between 1 and 12")


# {
#   責務: [EvidenceProvenance: output regionのdata source and inference claimを記録する]
#   フィールド: [region, kind, confidence, generator, note]
# }
@dataclass(frozen=True, slots=True)
class EvidenceProvenance:
    region: str
    kind: EvidenceKind
    confidence: float
    generator: str
    note: str = ""

    # {
    #   責務: [__post_init__: provenance labels and confidence rangeをvalidateする]
    #   処理: [require an explicit evidence kind and finite confidence]
    #   引数: [self: evidence source, region and confidence statement]
    #   戻り値: []
    #   エラー: [ValueError: malformed provenance]
    # }
    def __post_init__(self) -> None:
        if (
            not isinstance(self.region, str)
            or not self.region.strip()
            or not isinstance(self.generator, str)
            or not self.generator.strip()
        ):
            raise ValueError("provenance requires a region and generator name")
        if not isinstance(self.kind, EvidenceKind):
            raise TypeError("provenance kind must use EvidenceKind")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (float, int))
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("provenance confidence must be between zero and one")


# {
#   責務: [WeakSignalCandidate: one alternative image/video candidate and its evidenceを保持する]
#   フィールド: [candidate_id, mode, frames, provenance, confidence, generator, strength, scores]
# }
@dataclass(frozen=True, slots=True)
class WeakSignalCandidate:
    candidate_id: str
    mode: WeakSignalMode
    frames: tuple[bytes, ...]
    provenance: tuple[EvidenceProvenance, ...]
    confidence: float
    generator: str
    strength: float
    scores: tuple[tuple[str, float], ...] = ()
    components: tuple[tuple[str, tuple[bytes, ...]], ...] = ()

    # {
    #   責務: [__post_init__: candidate frame, evidence and score dataをvalidateする]
    #   処理: [require provenance and bounded score values without using one universal image-quality score]
    #   引数: [self: one candidate render with source accounting]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: malformed candidate]
    # }
    def __post_init__(self) -> None:
        if not self.candidate_id.strip() or not self.generator.strip():
            raise ValueError("candidate ID and generator must not be empty")
        if not isinstance(self.mode, WeakSignalMode) or self.mode is WeakSignalMode.AUTO:
            raise ValueError("candidate mode must be a resolved non-auto mode")
        if not self.frames or any(
            not isinstance(frame, bytes) or not frame for frame in self.frames
        ):
            raise ValueError("candidate must contain encoded output frames")
        if not self.provenance or any(
            not isinstance(item, EvidenceProvenance) for item in self.provenance
        ):
            raise ValueError("candidate must preserve evidence provenance")
        for value in (self.confidence, self.strength):
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError("candidate confidence/strength must be between zero and one")
        names = [name for name, _score in self.scores]
        if len(names) != len(set(names)) or any(
            not name.strip()
            or isinstance(score, bool)
            or not isinstance(score, (float, int))
            or not math.isfinite(score)
            or not 0 <= score <= 1
            for name, score in self.scores
        ):
            raise ValueError("candidate scores require unique names and finite zero-to-one values")
        component_names = [name for name, _frames in self.components]
        if len(component_names) != len(set(component_names)) or any(
            not name.strip()
            or not frames
            or any(not isinstance(frame, bytes) or not frame for frame in frames)
            for name, frames in self.components
        ):
            raise ValueError("candidate components require unique names and encoded frames")


# {
#   責務: [WeakSignalResult: resolved mode, alternatives and classifier evidenceを返す]
#   フィールド: [observation_id, selected_mode, candidates, mode_confidence, mode_reason]
# }
@dataclass(frozen=True, slots=True)
class WeakSignalResult:
    observation_id: str
    selected_mode: WeakSignalMode
    candidates: tuple[WeakSignalCandidate, ...]
    mode_confidence: float
    mode_reason: str

    # {
    #   責務: [__post_init__: resolved mode and ranked candidatesをvalidateする]
    #   処理: [ensure candidate provenance and confidence stay attached to the observation result]
    #   引数: [self: processed weak-signal result]
    #   戻り値: []
    #   エラー: [ValueError: malformed result]
    # }
    def __post_init__(self) -> None:
        if not self.observation_id.strip() or not self.mode_reason.strip():
            raise ValueError("weak-signal result requires an observation ID and mode reason")
        if (
            not isinstance(self.selected_mode, WeakSignalMode)
            or self.selected_mode is WeakSignalMode.AUTO
        ):
            raise ValueError("weak-signal result requires a resolved mode")
        if not self.candidates or any(
            not isinstance(item, WeakSignalCandidate) for item in self.candidates
        ):
            raise ValueError("weak-signal result requires one or more candidates")
        if (
            isinstance(self.mode_confidence, bool)
            or not isinstance(self.mode_confidence, (float, int))
            or not math.isfinite(self.mode_confidence)
            or not 0 <= self.mode_confidence <= 1
        ):
            raise ValueError("mode confidence must be between zero and one")
