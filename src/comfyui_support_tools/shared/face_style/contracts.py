"""Contracts for identity-preserving, face-local style retouching."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from PIL import Image


# {
# 責務: [FaceSelection: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class FaceSelection(str, Enum):
    MAIN = "main"
    SELECTED = "selected"
    ALL = "all"
    GROUP = "group"


# {
# 責務: [BangsPolicy: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class BangsPolicy(str, Enum):
    PRESERVE = "preserve"
    INCLUDE = "include"
    UNDER_HAIR = "under_hair"


# {
# 責務: [FaceStyleTarget: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
@dataclass(frozen=True)
class FaceStyleTarget:
    line_style: str = ""
    shading_style: str = ""
    medium: str = ""
    era: str = ""
    detail_density: str = ""
    stylization_strength: float = 0.5
    reference_style_image: str | None = None
    style_embedding: tuple[float, ...] = ()
    preserve_identity: bool = True
    preserve_expression: bool = True
    preserve_pose: bool = True
    preserve_gaze: bool = True
    preserve_hair: bool = True
    preserve_palette: bool = True
    bangs_policy: BangsPolicy = BangsPolicy.PRESERVE

    # {
    # 責務: [__post_init__: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def __post_init__(self) -> None:
        if not 0.0 <= self.stylization_strength <= 1.0:
            raise ValueError("stylization_strength must be between 0 and 1")
        if self.preserve_hair and self.bangs_policy == BangsPolicy.INCLUDE:
            raise ValueError("include bangs conflicts with preserve_hair")


# {
# 責務: [FaceRegion: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
@dataclass(frozen=True)
class FaceRegion:
    face_id: str
    face_mask: Image.Image
    hair_overlap_mask: Image.Image | None = None
    confidence: float = 1.0

    # {
    # 責務: [__post_init__: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def __post_init__(self) -> None:
        if not self.face_id.strip():
            raise ValueError("face_id is required")
        if self.face_mask.mode != "L":
            raise ValueError("face_mask must be a grayscale image")
        if self.hair_overlap_mask is not None:
            if (
                self.hair_overlap_mask.mode != "L"
                or self.hair_overlap_mask.size != self.face_mask.size
            ):
                raise ValueError("hair overlap mask must match face mask size and use L mode")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("face confidence must be between 0 and 1")


# {
# 責務: [FaceStyleRequest: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
@dataclass(frozen=True)
class FaceStyleRequest:
    image: Image.Image
    target: FaceStyleTarget
    regions: tuple[FaceRegion, ...] = ()
    selected_face_ids: tuple[str, ...] = ()
    selection: FaceSelection = FaceSelection.MAIN
    prompt: str = ""
    confidence_threshold: float = 0.75
    preserve_outside_mask: bool = True

    # {
    # 責務: [__post_init__: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def __post_init__(self) -> None:
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        if self.image.width * self.image.height > 50_000_000:
            raise ValueError("image exceeds the 50 megapixel safety limit")
        for region in self.regions:
            if region.face_mask.size != self.image.size:
                raise ValueError("face masks must match source image dimensions")
        if len({region.face_id for region in self.regions}) != len(self.regions):
            raise ValueError("face ids must be unique")


# {
# 責務: [FaceStyleMetrics: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
@dataclass(frozen=True)
class FaceStyleMetrics:
    style_match: float | None = None
    identity_preservation: float | None = None
    expression_preservation: float | None = None
    pose_preservation: float | None = None
    gaze_preservation: float | None = None
    non_target_preservation: float = 1.0
    details: dict[str, float] = field(default_factory=dict)

    # {
    # 責務: [safe_to_accept: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    @property
    def safe_to_accept(self) -> bool:
        required = (
            self.identity_preservation,
            self.expression_preservation,
            self.pose_preservation,
            self.non_target_preservation,
        )
        return all(value is not None and value >= 0.8 for value in required)


# {
# 責務: [FaceStyleCandidate: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
@dataclass(frozen=True)
class FaceStyleCandidate:
    image: Image.Image
    face_ids: tuple[str, ...]
    metrics: FaceStyleMetrics
    warnings: tuple[str, ...] = ()
    accepted: bool = False


# {
# 責務: [FaceStyleResult: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
@dataclass(frozen=True)
class FaceStyleResult:
    candidates: tuple[FaceStyleCandidate, ...]
    selected_index: int | None
    warnings: tuple[str, ...] = ()


# {
# 責務: [FaceRegionProvider: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class FaceRegionProvider(Protocol):
    # {
    # 責務: [find_faces: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, image]
    # 戻り値: [処理結果]
    # }
    def find_faces(self, image: Image.Image) -> tuple[FaceRegion, ...]: ...


# {
# 責務: [FaceStyleBackend: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class FaceStyleBackend(Protocol):
    name: str

    # {
    # 責務: [edit: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, image, mask, target, prompt]
    # 戻り値: [処理結果]
    # }
    def edit(
        self, image: Image.Image, mask: Image.Image, target: FaceStyleTarget, prompt: str
    ) -> Image.Image: ...


# {
# 責務: [FaceStyleEvaluator: face style retouch domain責務を提供する]
# フィールド: [定義済み契約または依存関係]
# 処理: [安全な顔領域style retouchを構成する]
# }
class FaceStyleEvaluator(Protocol):
    # {
    # 責務: [evaluate: face style retouchの処理または検証を行う]
    # 処理: [1: 入力を検証する, 2: 結果を返す]
    # 引数: [self, source, candidate, mask, target]
    # 戻り値: [処理結果]
    # }
    def evaluate(
        self,
        source: Image.Image,
        candidate: Image.Image,
        mask: Image.Image,
        target: FaceStyleTarget,
    ) -> FaceStyleMetrics: ...
