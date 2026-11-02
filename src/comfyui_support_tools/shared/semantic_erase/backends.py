"""Inpainting backend contracts, CPU baseline, and model adapter registry."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np
from PIL import Image

from comfyui_support_tools.shared.semantic_erase.contracts import (
    FillPolicy,
    QualityProfile,
    RLEMask,
    SemanticEraseTarget,
)


# {
# 責務: [InpaintResult: backend出力画像とbackend側の制約を返す]
# フィールド: [image,backend_id,warnings]
# }
@dataclass(frozen=True)
class InpaintResult:
    image: Image.Image
    backend_id: str
    warnings: tuple[str, ...] = ()


# {
# 責務: [InpaintBackend: mask-guided fillを提供する拡張protocol]
# フィールド: [なし]
# 処理: [1: originalとbinary maskに基づき非破壊candidateを生成する]
# }
class InpaintBackend(Protocol):
    # {
    # 責務: [inpaint: 指定maskだけを補完した画像candidateを生成する]
    # 処理: [1: fill strategyを解釈する, 2: 新しいimage candidateを返す]
    # 引数: [image: RGB source, mask: erase mask, target: semantic fill policy]
    # 戻り値: [result: inpainted image]
    # }
    def inpaint(
        self, image: Image.Image, mask: RLEMask, target: SemanticEraseTarget
    ) -> InpaintResult: ...


# {
# 責務: [OpenCVTeleaBackend: dependency-light local inpainting baselineを提供する]
# フィールド: [radius: neighborhood fill半径]
# 補足: [境界外のpixelを入力から復元し、target外の全体再生成を避ける]
# }
class OpenCVTeleaBackend:
    # {
    # 責務: [__init__: Telea neighborhood radiusを検証する]
    # 処理: [1: radiusの安全なpixel範囲を確認する]
    # 引数: [radius: OpenCV inpaint radius]
    # 戻り値: []
    # エラー: [ValueError: radiusが範囲外の場合]
    # }
    def __init__(self, radius: int = 3):
        if isinstance(radius, bool) or not isinstance(radius, int) or not 1 <= radius <= 32:
            raise ValueError("inpaint radius must be an integer between 1 and 32")
        self.radius = radius

    # {
    # 責務: [inpaint: OpenCV Teleaでmask regionを補完する]
    # 処理: [1: image/maskをRGB/uint8へ正規化する, 2: Telea fillを行う, 3: mask外をsource pixelに復元する]
    # 引数: [image: source RGB image, mask: erase mask, target: fill policy]
    # 戻り値: [result: local inpaint candidate]
    # エラー: [ValueError: image/mask dimensionsが不一致の場合]
    # }
    def inpaint(
        self, image: Image.Image, mask: RLEMask, target: SemanticEraseTarget
    ) -> InpaintResult:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        binary = (
            np.frombuffer(mask.to_binary_bytes(), dtype=np.uint8).reshape(mask.height, mask.width)
            * 255
        )
        if binary.shape != rgb.shape[:2] or not binary.any():
            raise ValueError("inpaint mask must be non-empty and match the image")
        filled = cv2.inpaint(
            cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), binary, self.radius, cv2.INPAINT_TELEA
        )
        output = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB)
        outside = binary == 0
        output[outside] = rgb[outside]
        warnings = ()
        if target.fill_policy is FillPolicy.CUSTOM:
            warnings = ("CPU baseline cannot follow free-form fill instructions",)
        elif target.fill_policy in {FillPolicy.RESTORE_SKIN, FillPolicy.RESTORE_CLOTH}:
            warnings = (
                "CPU baseline is texture interpolation, not semantic skin/cloth restoration",
            )
        return InpaintResult(Image.fromarray(output), "opencv-telea", warnings)


# {
# 責務: [CallableInpaintBackend: model host callableをbackend protocolへ適合させる]
# フィールド: [backend_id,processor: injected model adapter]
# }
class CallableInpaintBackend:
    # {
    # 責務: [__init__: model implementation callbackを保持する]
    # 処理: [1: backend IDとcallableを検証して保持する]
    # 引数: [backend_id: stable descriptor, processor: image/mask/target callback]
    # 戻り値: []
    # エラー: [ValueError: IDが空の場合]
    # }
    def __init__(
        self,
        backend_id: str,
        processor: Callable[[Image.Image, RLEMask, SemanticEraseTarget], Image.Image],
    ):
        if not backend_id.strip():
            raise ValueError("backend ID must not be empty")
        self.backend_id = backend_id
        self._processor = processor

    # {
    # 責務: [inpaint: injected modelへmask-guided fillを委譲する]
    # 処理: [1: model processorを呼ぶ, 2: output type/sizeを検証する]
    # 引数: [image: source RGB image, mask: erase mask, target: semantic fill policy]
    # 戻り値: [result: validated inpaint result]
    # エラー: [ValueError: output imageがinput sizeと異なる場合]
    # }
    def inpaint(
        self, image: Image.Image, mask: RLEMask, target: SemanticEraseTarget
    ) -> InpaintResult:
        result = self._processor(image.copy(), mask, target)
        if not isinstance(result, Image.Image) or result.size != image.size:
            raise ValueError(f"{self.backend_id} returned an invalid image")
        return InpaintResult(result.convert("RGB"), self.backend_id)


# {
# 責務: [InpaintBackendRegistry: pluggable erase modelを安定IDで登録する]
# フィールド: [backends: available local/remote inpaint implementations]
# }
class InpaintBackendRegistry:
    # {
    # 責務: [__init__: 空のbackend registryを作成する]
    # 処理: [1: backend mapを初期化する]
    # 引数: [self: registry]
    # 戻り値: []
    # }
    def __init__(self):
        self._backends: dict[str, InpaintBackend] = {}

    # {
    # 責務: [register: inpaint backendをstable IDへ登録する]
    # 処理: [1: 空IDと重複を検証する, 2: backendを登録する]
    # 引数: [backend_id: stable ID, backend: protocol implementation]
    # 戻り値: []
    # エラー: [ValueError: IDが空または重複する場合]
    # }
    def register(self, backend_id: str, backend: InpaintBackend) -> None:
        key = backend_id.strip()
        if not key or key in self._backends:
            raise ValueError("inpaint backend ID must be unique and non-empty")
        self._backends[key] = backend

    # {
    # 責務: [route: profileに応じたinpaint backend candidatesを返す]
    # 処理: [1: CPU fallbackを必ず加える, 2: quality profile budgetを適用する]
    # 引数: [profile: quality profile]
    # 戻り値: [backends: deterministic ordered backend candidates]
    # }
    def route(self, profile: QualityProfile) -> tuple[tuple[str, InpaintBackend], ...]:
        ordered = tuple(
            (key, self._backends[key])
            for key in sorted(self._backends, key=lambda item: (item != "opencv-telea", item))
        )
        if profile is QualityProfile.FAST:
            return ordered[:1]
        return ordered

    # {
    # 責務: [named_backends: documented model backend IDs available from host registration]
    # 処理: [1: standard extension labelsを返す]
    # 引数: [self: registry]
    # 戻り値: [ids: registered backend names]
    # }
    def named_backends(self) -> tuple[str, ...]:
        return tuple(sorted(self._backends))


# {
# 責務: [create_default_backend_registry: safe CPU fallbackを含むregistryを作る]
# 処理: [1: OpenCV Telea backendを登録する]
# 引数: [radius: local fill radius]
# 戻り値: [registry: initialized backend registry]
# }
def create_default_backend_registry(radius: int = 3) -> InpaintBackendRegistry:
    registry = InpaintBackendRegistry()
    registry.register("opencv-telea", OpenCVTeleaBackend(radius))
    return registry


# {
# 責務: [mask_variants: tight/expanded/soft edge mask候補を作成する]
# 処理: [1: maskを画像sizeへ復元する, 2: profile budgetとsizeに応じdilation候補を返す]
# 引数: [mask: input mask, profile: quality budget, max_variants: upper bound]
# 戻り値: [variants: uniquely encoded mask candidates]
# }
def mask_variants(
    mask: RLEMask, profile: QualityProfile, max_variants: int = 4
) -> tuple[RLEMask, ...]:
    if not 1 <= max_variants <= 8:
        raise ValueError("mask variant limit must be between 1 and 8")
    source = np.frombuffer(mask.to_binary_bytes(), dtype=np.uint8).reshape(mask.height, mask.width)
    radius_by_profile = {
        QualityProfile.FAST: (0,),
        QualityProfile.STANDARD: (0, 1),
        QualityProfile.QUALITY: (0, 1, 2),
        QualityProfile.OVERNIGHT: (0, 1, 2, 4),
    }[profile]
    variants = []
    for radius in radius_by_profile[:max_variants]:
        if radius == 0:
            expanded = source
        else:
            size = radius * 2 + 1
            kernel = np.ones((size, size), dtype=np.uint8)
            expanded = cv2.dilate(source, kernel, iterations=1)
        encoded = RLEMask.from_binary_bytes(mask.width, mask.height, expanded.tobytes())
        if encoded not in variants:
            variants.append(encoded)
    return tuple(variants)


# {
# 責務: [edit_mask_stroke: user scribbleでmaskを追加または削除する]
# 処理: [1: point座標をpixelへ変換する, 2: brush strokeをmaskへ反映する]
# 引数: [mask: current mask, points: normalized path, radius: normalized brush radius, erase: subtract stroke]
# 戻り値: [edited: user-corrected mask]
# エラー: [ValueError: path pointまたはradiusが範囲外の場合]
# }
def edit_mask_stroke(
    mask: RLEMask,
    points: tuple[tuple[float, float], ...],
    radius: float = 0.01,
    *,
    erase: bool = False,
) -> RLEMask:
    if not 0 < radius <= 0.5:
        raise ValueError("brush radius must be between 0 and 0.5")
    if not points:
        return mask
    if any(not 0 <= x <= 1 or not 0 <= y <= 1 for x, y in points):
        raise ValueError("brush points must use normalized image coordinates")
    canvas = (
        np.frombuffer(mask.to_binary_bytes(), dtype=np.uint8).reshape(mask.height, mask.width) * 255
    )
    stroke = np.zeros_like(canvas)
    pixel_points = [(round(x * (mask.width - 1)), round(y * (mask.height - 1))) for x, y in points]
    thickness = max(1, round(radius * 2 * min(mask.width, mask.height)))
    for first, second in zip(pixel_points, pixel_points[1:], strict=False):
        cv2.line(stroke, first, second, 255, thickness, lineType=cv2.LINE_AA)
    if len(pixel_points) == 1:
        cv2.circle(stroke, pixel_points[0], max(1, thickness // 2), 255, -1)
    result = (
        cv2.bitwise_and(canvas, cv2.bitwise_not(stroke))
        if erase
        else cv2.bitwise_or(canvas, stroke)
    )
    return RLEMask.from_binary_bytes(
        mask.width, mask.height, (result > 0).astype(np.uint8).tobytes()
    )
