"""Composable semantic grounding and segmentation provider adapters."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL import Image

from comfyui_support_tools.shared.semantic_erase.contracts import (
    RegionBox,
    RegionCandidate,
    RLEMask,
    SemanticEraseTarget,
)

MAX_REGION_CANDIDATES = 128


# {
# 責務: [TextDetection: open-vocabulary detection結果を表現する]
# フィールド: [box,confidence,label: detected region evidence]
# }
@dataclass(frozen=True)
class TextDetection:
    box: RegionBox
    confidence: float
    label: str


# {
# 責務: [RegionProvider: text queryからmask候補を提案する拡張protocol]
# フィールド: [なし]
# 処理: [1: 画像とtarget queryを解析してcandidateを返す]
# }
class RegionProvider(Protocol):
    # {
    # 責務: [propose: imageとsemantic targetからmask候補を生成する]
    # 処理: [1: provider固有のregion evidenceを評価する, 2: confidence付きmaskを返す]
    # 引数: [image: input RGB image, target: erase target]
    # 戻り値: [candidates: region mask候補]
    # }
    def propose(
        self, image: Image.Image, target: SemanticEraseTarget
    ) -> Sequence[RegionCandidate]: ...


# {
# 責務: [RegionProviderRegistry: providerを安定IDで登録し取得する]
# フィールド: [providers: semantic region providers]
# }
class RegionProviderRegistry:
    # {
    # 責務: [__init__: 空のprovider registryを初期化する]
    # 処理: [1: provider mapを初期化する]
    # 引数: [self: registry]
    # 戻り値: []
    # }
    def __init__(self):
        self._providers: dict[str, RegionProvider] = {}

    # {
    # 責務: [register: semantic region providerをIDへ登録する]
    # 処理: [1: IDの重複と空文字を拒否する, 2: providerを登録する]
    # 引数: [provider_id: stable ID, provider: region provider]
    # 戻り値: []
    # エラー: [ValueError: IDが空または重複する場合]
    # }
    def register(self, provider_id: str, provider: RegionProvider) -> None:
        key = provider_id.strip()
        if not key or key in self._providers:
            raise ValueError("region provider ID must be unique and non-empty")
        self._providers[key] = provider

    # {
    # 責務: [providers: ID順にprovider一覧を返す]
    # 処理: [1: stable ID順でproviderを返す]
    # 引数: [self: registry]
    # 戻り値: [providers: provider tuple]
    # }
    def providers(self) -> tuple[tuple[str, RegionProvider], ...]:
        return tuple((key, self._providers[key]) for key in sorted(self._providers))


# {
# 責務: [TextGroundingDetector: open-vocabulary bounding box detector protocol]
# フィールド: [なし]
# 処理: [1: text queryに合うboxを画像から検出する]
# }
class TextGroundingDetector(Protocol):
    # {
    # 責務: [detect: imageとqueryからobject/attribute boxを検出する]
    # 処理: [1: queryをgroundする, 2: score付きboxを返す]
    # 引数: [image: RGB image, query: natural language text]
    # 戻り値: [detections: text detection tuple]
    # }
    def detect(self, image: Image.Image, query: str) -> Sequence[TextDetection]: ...


# {
# 責務: [MaskSegmenter: boxとqueryからinstance maskを作るprotocol]
# フィールド: [なし]
# 処理: [1: prompt boxをsegmentation maskへ変換する]
# }
class MaskSegmenter(Protocol):
    # {
    # 責務: [segment: detector boxをinstance maskへ変換する]
    # 処理: [1: imageとboxをsegmentation modelへ渡す]
    # 引数: [image: RGB image, box: normalized detection box]
    # 戻り値: [mask: HxW binary array]
    # }
    def segment(self, image: Image.Image, box: RegionBox) -> np.ndarray: ...


# {
# 責務: [GroundedSegmentationProvider: text detectorとsegmenterを連結する]
# フィールド: [detector,segmenter,provider_id]
# 処理: [1: queryをgroundingする, 2: 各boxをmask化する]
# }
class GroundedSegmentationProvider:
    # {
    # 責務: [__init__: detector/segmenter adapterを保持する]
    # 処理: [1: injected model adaptersを保持する]
    # 引数: [detector: text-grounding adapter, segmenter: promptable segmentation adapter, provider_id: stable name]
    # 戻り値: []
    # }
    def __init__(
        self,
        detector: TextGroundingDetector,
        segmenter: MaskSegmenter,
        provider_id: str = "grounded-segmentation",
    ):
        if not provider_id.strip():
            raise ValueError("provider ID must not be empty")
        self.detector = detector
        self.segmenter = segmenter
        self.provider_id = provider_id

    # {
    # 責務: [propose: text detectionとsegmentationを組み合わせる]
    # 処理: [1: queryを検出する, 2: boxをmask化する, 3: shapeを検証して候補化する]
    # 引数: [image: source image, target: semantic erase target]
    # 戻り値: [candidates: mask candidate tuple]
    # }
    def propose(
        self, image: Image.Image, target: SemanticEraseTarget
    ) -> tuple[RegionCandidate, ...]:
        candidates = []
        query = target.provider_query or target.normalized_tag or target.query
        for detection in self.detector.detect(image, query):
            mask = np.asarray(self.segmenter.segment(image, detection.box), dtype=bool)
            if mask.shape != (image.height, image.width):
                continue
            mask &= _box_mask(image.width, image.height, detection.box)
            if not mask.any():
                continue
            candidates.append(
                RegionCandidate(
                    mask=_to_rle(mask),
                    confidence=float(detection.confidence),
                    provider=self.provider_id,
                    evidence=(detection.label or target.query,),
                )
            )
        return tuple(candidates)


# {
# 責務: [AttributeStateFallbackProvider: bruise/stain等の属性候補を作るadapter]
# フィールド: [infer: VLM/tagger/face-parser複合fallback]
# 補足: [検出モデルを外部runtimeから注入し、単一VLMのboxを確定maskと扱わない]
# }
class AttributeStateFallbackProvider:
    # {
    # 責務: [__init__: attribute inference callableを保持する]
    # 処理: [1: callableとstable provider IDを保持する]
    # 引数: [infer: image/queryからregion candidatesを返すcallable, provider_id: provider name]
    # 戻り値: []
    # }
    def __init__(
        self,
        infer: Callable[[Image.Image, str], Sequence[tuple[np.ndarray, float, str]]],
        provider_id: str = "attribute-state-fallback",
    ):
        self._infer = infer
        self.provider_id = provider_id

    # {
    # 責務: [propose: attribute/state fallback resultを検証可能candidateへ変換する]
    # 処理: [1: query fallbackを呼ぶ, 2: mask shapeとareaを確認する, 3: provenance付きcandidateを返す]
    # 引数: [image: source image, target: semantic erase target]
    # 戻り値: [candidates: attribute/state candidates]
    # }
    def propose(
        self, image: Image.Image, target: SemanticEraseTarget
    ) -> tuple[RegionCandidate, ...]:
        candidates = []
        query = target.provider_query or target.normalized_tag or target.query
        for raw_mask, confidence, evidence in self._infer(image, query):
            mask = np.asarray(raw_mask, dtype=bool)
            if mask.shape != (image.height, image.width) or not mask.any():
                continue
            candidates.append(
                RegionCandidate(
                    _to_rle(mask), float(confidence), self.provider_id, evidence=(evidence,)
                )
            )
        return tuple(candidates)


# {
# 責務: [_to_rle: HxW boolean arrayをversioned mask contractへ変換する]
# 処理: [1: arrayをbool gridへ変換する, 2: RLEMaskを作る]
# 引数: [mask: two-dimensional binary mask]
# 戻り値: [encoded: encoded mask]
# エラー: [ValueError: mask次元が2D以外の場合]
# }
def _to_rle(mask: np.ndarray) -> RLEMask:
    if mask.ndim != 2:
        raise ValueError("candidate mask must be a 2D array")
    normalized = np.ascontiguousarray(mask, dtype=np.uint8)
    return RLEMask.from_binary_bytes(mask.shape[1], mask.shape[0], normalized.tobytes())


# {
# 責務: [_box_mask: normalized detection boxをbinary crop constraintへ変換する]
# 処理: [1: floating-point edgeをpixel boundsへ丸める, 2: box内pixelだけを有効にする]
# 引数: [width: image width, height: image height, box: normalized detection]
# 戻り値: [mask: box region constraint]
# }
def _box_mask(width: int, height: int, box: RegionBox) -> np.ndarray:
    epsilon = 1e-9
    left = max(0, int(np.floor(box.x * width + epsilon)))
    top = max(0, int(np.floor(box.y * height + epsilon)))
    right = min(width, int(np.ceil((box.x + box.width) * width - epsilon)))
    bottom = min(height, int(np.ceil((box.y + box.height) * height - epsilon)))
    mask = np.zeros((height, width), dtype=bool)
    mask[top:bottom, left:right] = True
    return mask


# {
# 責務: [apply_range_constraint: candidate maskをユーザーのspatial rangeで制限する]
# 処理: [1: normalized boxをpixel boundsへ写す, 2: candidate maskとboxをANDする]
# 引数: [candidate: input mask candidate, region: normalized range]
# 戻り値: [constrained: range内maskまたは空の場合None]
# }
def apply_range_constraint(
    candidate: RegionCandidate, region: RegionBox | None
) -> RegionCandidate | None:
    if region is None:
        return candidate
    mask = (
        np.frombuffer(candidate.mask.to_binary_bytes(), dtype=np.uint8)
        .reshape(candidate.mask.height, candidate.mask.width)
        .astype(bool)
    )
    height, width = mask.shape
    constrained = np.logical_and(mask, _box_mask(width, height, region))
    if not constrained.any():
        return None
    return RegionCandidate(
        _to_rle(constrained),
        candidate.confidence,
        candidate.provider,
        candidate.match_id,
        candidate.evidence + ("range-constrained",),
    )


# {
# 責務: [resolve_region_candidates: providers/manual maskをmergeしrangeと重複を整理する]
# 処理: [1: manual maskを優先する, 2: provider evidenceを集める, 3: range/NMS後にconfidence順で返す]
# 引数: [image: source image, target: erase request, registry: region provider registry]
# 戻り値: [candidates: deterministic selected proposals]
# }
def resolve_region_candidates(
    image: Image.Image,
    target: SemanticEraseTarget,
    registry: RegionProviderRegistry,
) -> tuple[RegionCandidate, ...]:
    if target.mask is not None:
        if (target.mask.width, target.mask.height) != image.size:
            raise ValueError("manual mask dimensions must match the source image")
        raw = RegionCandidate(target.mask, 1.0, "manual-mask", evidence=("user-corrected",))
        constrained = apply_range_constraint(raw, target.range_constraint)
        return (constrained,) if constrained else ()

    candidates = []
    for provider_id, provider in registry.providers():
        for candidate in provider.propose(image, target):
            if candidate.mask.width != image.width or candidate.mask.height != image.height:
                continue
            if candidate.provider != provider_id:
                # Keep registry identity authoritative for reproducible audits.
                candidate = RegionCandidate(
                    candidate.mask,
                    candidate.confidence,
                    provider_id,
                    candidate.match_id,
                    candidate.evidence,
                )
            constrained = apply_range_constraint(candidate, target.range_constraint)
            if constrained is not None and constrained.confidence >= target.confidence_threshold:
                candidates.append(constrained)
                if len(candidates) >= MAX_REGION_CANDIDATES:
                    break
        if len(candidates) >= MAX_REGION_CANDIDATES:
            break
    candidates.sort(key=lambda item: (-item.confidence, item.provider, item.match_id))
    return _deduplicate(candidates)


# {
# 責務: [_deduplicate: 同一の領域を返す複数provider候補を統合する]
# 処理: [1: confidence順候補を走査する, 2: IoUが閾値を超える重複を除外する]
# 引数: [candidates: score順candidate列]
# 戻り値: [selected: NMS後の候補tuple]
# }
def _deduplicate(candidates: Sequence[RegionCandidate], iou_threshold: float = 0.85):
    kept: list[RegionCandidate] = []
    kept_masks = []
    for candidate in candidates:
        duplicate = False
        left = (
            np.frombuffer(candidate.mask.to_binary_bytes(), dtype=np.uint8)
            .reshape(candidate.mask.height, candidate.mask.width)
            .astype(bool)
        )
        for right in kept_masks:
            intersection = int(np.logical_and(left, right).sum())
            union = int(np.logical_or(left, right).sum())
            if union and intersection / union >= iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
            kept_masks.append(left)
    return tuple(kept)
