"""Contracts for localized facial-expression editing."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from numbers import Real
from typing import Protocol

NormalizedBox = tuple[float, float, float, float]


# {
#   責務: [ExpressionPreset: supported structured expression targets]
#   フィールド: [neutral, smile, laugh, angry, sad, crying, surprised, embarrassed, worried, sleepy, wink, smirk, shout]
#   処理: [map UI and natural-language intents to a stable target identifier]
# }
class ExpressionPreset(str, Enum):
    NEUTRAL = "neutral"
    SLIGHT_SMILE = "slight_smile"
    SMILE = "smile"
    LAUGH = "laugh"
    ANGRY = "angry"
    SAD = "sad"
    CRYING = "crying"
    SURPRISED = "surprised"
    EMBARRASSED = "embarrassed"
    WORRIED = "worried"
    SLEEPY = "sleepy"
    WINK_LEFT = "wink_left"
    WINK_RIGHT = "wink_right"
    SMIRK = "smirk"
    SHOUT = "shout"


# {
#   責務: [ExpressionMode: choose appearance-specific retouch constraints]
#   フィールド: [ANIME, PHOTOREAL]
#   処理: [route face-preservation expectations for illustration or photography]
# }
class ExpressionMode(str, Enum):
    ANIME = "anime"
    PHOTOREAL = "photoreal"


# {
#   責務: [FacePart: define supported localized edit regions]
#   フィールド: [FULL_FACE, LEFT_EYE, RIGHT_EYE, EYES, EYEBROWS, MOUTH, CHEEKS, TEAR_REGION]
#   処理: [allow a request to edit all face or selected facial components]
# }
class FacePart(str, Enum):
    FULL_FACE = "full_face"
    LEFT_EYE = "left_eye"
    RIGHT_EYE = "right_eye"
    EYES = "eyes"
    EYEBROWS = "eyebrows"
    MOUTH = "mouth"
    CHEEKS = "cheeks"
    TEAR_REGION = "tear_region"


# {
#   責務: [ExpressionParameters: store bounded controls for individual face muscles]
#   フィールド: [smile, mouth, eye, eyebrow, blush, tear, gaze controls]
#   処理: [keep explicit controls independent from natural-language target text]
# }
@dataclass(frozen=True)
class ExpressionParameters:
    smile_strength: float | None = None
    mouth_open: float | None = None
    eye_openness_left: float | None = None
    eye_openness_right: float | None = None
    eyebrow_raise_left: float | None = None
    eyebrow_raise_right: float | None = None
    eyebrow_inward: float | None = None
    blush_strength: float | None = None
    tear_strength: float | None = None
    gaze_x: float | None = None
    gaze_y: float | None = None

    # {
    #   責務: [__post_init__: reject non-finite or out-of-range facial controls]
    #   処理: [1: inspect every optional parameter, 2: require values in the unit interval]
    #   引数: [self: expression parameter set]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if name in {"gaze_x", "gaze_y"}:
                if value is not None and (
                    isinstance(value, bool)
                    or not isinstance(value, Real)
                    or not math.isfinite(value)
                    or not -1 <= value <= 1
                ):
                    raise ValueError(f"{name} must be between -1 and 1")
                continue
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{name} must be between 0 and 1")


# {
#   責務: [FacePartRegion: identify a normalized facial edit rectangle]
#   フィールド: [part, bbox, confidence]
#   処理: [represent detector estimates and user-selected local mask targets]
# }
@dataclass(frozen=True)
class FacePartRegion:
    part: FacePart
    bbox: NormalizedBox
    confidence: float

    # {
    #   責務: [__post_init__: validate one face part localization]
    #   処理: [check finite normalized geometry and confidence]
    #   引数: [self: face part region]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        _validate_box(self.bbox)
        _validate_score(self.confidence, "confidence")


# {
#   責務: [DetectedFace: store one ordered detected face and estimated part regions]
#   フィールド: [index, bbox, confidence, parts]
#   処理: [keep face selection and local region geometry in normalized image coordinates]
# }
@dataclass(frozen=True)
class DetectedFace:
    index: int
    bbox: NormalizedBox
    confidence: float
    parts: tuple[FacePartRegion, ...]

    # {
    #   責務: [__post_init__: validate detector output]
    #   処理: [require a nonnegative index, normalized box, and bounded confidence]
    #   引数: [self: face record]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or isinstance(self.index, bool) or self.index < 0:
            raise ValueError("face index must be nonnegative")
        _validate_box(self.bbox)
        _validate_score(self.confidence, "confidence")
        if any(not isinstance(part, FacePartRegion) for part in self.parts):
            raise ValueError("face parts must contain FacePartRegion values")


# {
#   責務: [FaceAnalysis: report all targetable faces and detector limitations]
#   フィールド: [image size, stable face list, warnings]
#   処理: [provide ordered detections for multi-face selection and preview overlays]
# }
@dataclass(frozen=True)
class FaceAnalysis:
    image_size: tuple[int, int]
    faces: tuple[DetectedFace, ...]
    warnings: tuple[str, ...] = ()

    # {
    #   責務: [__post_init__: validate image analysis dimensions and detections]
    #   処理: [require positive dimensions, typed faces, and textual warnings]
    #   引数: [self: face analysis result]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if len(self.image_size) != 2 or any(
            not isinstance(size, int) or isinstance(size, bool) or size <= 0
            for size in self.image_size
        ):
            raise ValueError("image_size must contain two positive integers")
        if any(not isinstance(face, DetectedFace) for face in self.faces):
            raise ValueError("faces must contain DetectedFace values")
        if any(not isinstance(warning, str) for warning in self.warnings):
            raise ValueError("warnings must contain strings")


# {
#   責務: [ExpressionEditRequest: define one localized facial expression edit]
#   フィールド: [source image, target, face, regions, mode, controls, preservation, candidates, seed]
#   処理: [keep face expression intent separate from the editing backend]
# }
@dataclass(frozen=True)
class ExpressionEditRequest:
    source_image: bytes
    target: ExpressionPreset
    intensity: float = 0.65
    mode: ExpressionMode = ExpressionMode.ANIME
    face_index: int = 0
    edit_regions: tuple[FacePart, ...] = (FacePart.FULL_FACE,)
    parameters: ExpressionParameters = ExpressionParameters()
    natural_language: str = ""
    preserve_identity: float = 0.9
    preserve_background: bool = True
    candidate_count: int = 3
    denoise: float = 0.35
    seed: int | None = None
    manual_mask: bytes | None = None

    # {
    #   責務: [__post_init__: validate one bounded local expression request]
    #   処理: [1: validate image and face controls, 2: bound candidate and denoise settings]
    #   引数: [self: immutable edit request]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_image, bytes)
            or not 1 <= len(self.source_image) <= 64 * 1024 * 1024
        ):
            raise ValueError("source image must contain 1..64 MiB")
        if not isinstance(self.target, ExpressionPreset) or not isinstance(
            self.mode, ExpressionMode
        ):
            raise ValueError("target and mode must use supported expression enums")
        if (
            not isinstance(self.face_index, int)
            or isinstance(self.face_index, bool)
            or self.face_index < 0
        ):
            raise ValueError("face_index must be a nonnegative integer")
        _validate_score(self.intensity, "intensity")
        _validate_score(self.preserve_identity, "preserve_identity")
        _validate_score(self.denoise, "denoise")
        if (
            not isinstance(self.candidate_count, int)
            or isinstance(self.candidate_count, bool)
            or not 1 <= self.candidate_count <= 8
        ):
            raise ValueError("candidate_count must be in 1..8")
        if (
            not self.edit_regions
            or any(not isinstance(part, FacePart) for part in self.edit_regions)
            or len(set(self.edit_regions)) != len(self.edit_regions)
        ):
            raise ValueError("edit_regions must be nonempty and unique")
        if not isinstance(self.parameters, ExpressionParameters):
            raise ValueError("parameters must use ExpressionParameters")
        if not isinstance(self.natural_language, str) or len(self.natural_language) > 2000:
            raise ValueError("natural_language must not exceed 2000 characters")
        if not isinstance(self.preserve_background, bool):
            raise ValueError("preserve_background must be a boolean")
        if self.seed is not None and (
            not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0
        ):
            raise ValueError("seed must be a nonnegative integer")
        if self.manual_mask is not None and (
            not isinstance(self.manual_mask, bytes)
            or not 1 <= len(self.manual_mask) <= 64 * 1024 * 1024
        ):
            raise ValueError("manual mask must contain 1..64 MiB")


# {
#   責務: [ExpressionBackendCapabilities: describe model modes and local edit support]
#   フィールド: [appearance modes, local mask, identity reference, instruction edit, resolution, VRAM]
#   処理: [route only requests supported by a backend's declared capabilities]
# }
@dataclass(frozen=True)
class ExpressionBackendCapabilities:
    modes: tuple[ExpressionMode, ...]
    local_mask: bool
    identity_reference: bool
    instruction_edit: bool
    max_resolution: int
    recommended_vram_gb: float | None = None

    # {
    #   責務: [__post_init__: validate backend capability metadata]
    #   処理: [require modes, resolution and optional VRAM to be valid]
    #   引数: [self: backend capabilities]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if (
            not self.modes
            or any(not isinstance(mode, ExpressionMode) for mode in self.modes)
            or len(set(self.modes)) != len(self.modes)
            or not isinstance(self.max_resolution, int)
            or isinstance(self.max_resolution, bool)
            or self.max_resolution < 64
        ):
            raise ValueError("backend must advertise modes and a useful maximum resolution")
        if any(
            not isinstance(value, bool)
            for value in (self.local_mask, self.identity_reference, self.instruction_edit)
        ):
            raise ValueError("backend support flags must be booleans")
        if self.recommended_vram_gb is not None and (
            isinstance(self.recommended_vram_gb, bool)
            or not isinstance(self.recommended_vram_gb, Real)
            or not math.isfinite(self.recommended_vram_gb)
            or self.recommended_vram_gb <= 0
        ):
            raise ValueError("recommended VRAM must be a positive finite number")


# {
#   責務: [ExpressionRetouchBackend: define replaceable masked-edit backends]
#   フィールド: [backend_id, capabilities, edit callable]
#   処理: [allow ComfyUI inpaint, instruction editors, and future model families]
# }
class ExpressionRetouchBackend(Protocol):
    # {
    #   責務: [backend_id: expose a stable backend identifier]
    #   処理: [return the registered backend name]
    #   引数: [self: backend]
    #   戻り値: [str: stable name]
    # }
    @property
    def backend_id(self) -> str: ...

    # {
    #   責務: [capabilities: expose supported editing modes]
    #   処理: [return model/edit constraints]
    #   引数: [self: backend]
    #   戻り値: [ExpressionBackendCapabilities: capabilities]
    # }
    @property
    def capabilities(self) -> ExpressionBackendCapabilities: ...

    # {
    #   責務: [edit: produce one masked expression candidate]
    #   処理: [preserve source pixels outside mask when the model supports local compositing]
    #   引数: [request: edit intent, mask: normalized grayscale PNG, seed: candidate seed]
    #   戻り値: [bytes: encoded candidate image]
    # }
    def edit(self, request: ExpressionEditRequest, mask: bytes, seed: int | None) -> bytes: ...


# {
#   責務: [ExpressionEvaluation: report expression and preservation signals]
#   フィールド: [expression, identity, non-target, locality scores, issues, limitations]
#   処理: [separate measured image-difference proxies from unavailable semantic model scores]
# }
@dataclass(frozen=True)
class ExpressionEvaluation:
    expression_match: float | None
    identity_preservation: float
    non_target_preservation: float
    locality: float
    visual_quality: float | None = None
    issues: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    # {
    #   責務: [__post_init__: validate evaluation scores]
    #   処理: [require every available quality signal to be within the unit interval]
    #   引数: [self: evaluation report]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        for name in (
            "expression_match",
            "identity_preservation",
            "non_target_preservation",
            "locality",
            "visual_quality",
        ):
            value = getattr(self, name)
            if value is not None:
                _validate_score(value, name)

    # {
    #   責務: [ranking_score: combine available signals without inventing expression accuracy]
    #   処理: [1: weight identity/locality, 2: include expression only when a semantic evaluator supplied it]
    #   引数: [self: evaluation report]
    #   戻り値: [float: comparable ranking score]
    # }
    @property
    def ranking_score(self) -> float:
        values = [
            0.4 * self.identity_preservation,
            0.3 * self.non_target_preservation,
            0.3 * self.locality,
        ]
        if self.expression_match is not None:
            values.extend((0.5 * self.expression_match,))
            return sum(values) / 1.5
        return sum(values)


# {
#   責務: [ExpressionSemanticEvaluator: define pluggable target-match and identity scoring]
#   フィールド: [evaluate callable]
#   処理: [allow CLIP/face embedding/expression classifier evaluation without binding a model family]
# }
class ExpressionSemanticEvaluator(Protocol):
    # {
    #   責務: [evaluate: score target expression and identity preservation]
    #   処理: [compare source and candidate in face/mask context]
    #   引数: [request: requested target, face: selected face, source: canonical image, candidate: raw generated image, mask: editable region]
    #   戻り値: [ExpressionEvaluation: semantic and visual quality signals]
    # }
    def evaluate(
        self,
        request: ExpressionEditRequest,
        face: DetectedFace,
        source: bytes,
        candidate: bytes,
        mask: bytes,
    ) -> ExpressionEvaluation: ...


# {
#   責務: [ExpressionCandidate: store one immutable retouch candidate and metadata]
#   フィールド: [path, backend, seed, mask path, evaluation]
#   処理: [support candidate comparison, selection, and reproducible history]
# }
@dataclass(frozen=True)
class ExpressionCandidate:
    image_path: str
    mask_path: str
    manifest_path: str
    backend_id: str
    seed: int | None
    evaluation: ExpressionEvaluation


# {
#   責務: [ExpressionRetouchResult: return the source, ordered candidates, and selection]
#   フィールド: [source hash, target, face list, candidate list, selected index, warnings]
#   処理: [keep edit history reproducible and allow later candidate selection]
# }
@dataclass(frozen=True)
class ExpressionRetouchResult:
    source_sha256: str
    target: ExpressionPreset
    faces: tuple[DetectedFace, ...]
    candidates: tuple[ExpressionCandidate, ...]
    selected_candidate: int
    warnings: tuple[str, ...] = ()


# {
#   責務: [_validate_box: enforce a finite normalized image rectangle]
#   処理: [1: validate tuple length and numeric values, 2: check positive in-bounds extent]
#   引数: [box: normalized x/y/width/height]
#   戻り値: []
# }
def _validate_box(box: NormalizedBox) -> None:
    if (
        not isinstance(box, tuple)
        or len(box) != 4
        or any(
            isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)
            for value in box
        )
    ):
        raise ValueError("face region must contain four finite values")
    x, y, width, height = box
    if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
        raise ValueError("face region must be a positive normalized box")


# {
#   責務: [_validate_score: validate one finite unit-interval score]
#   処理: [reject non-finite or out-of-range scores]
#   引数: [value: score value, name: user-facing field name]
#   戻り値: []
# }
def _validate_score(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"{name} must be between 0 and 1")
