"""Non-target preservation, residual target, and boundary scoring."""

import cv2
import numpy as np
from PIL import Image

from comfyui_support_tools.shared.semantic_erase.contracts import (
    EraseEvaluation,
    RLEMask,
    SemanticEraseTarget,
)
from comfyui_support_tools.shared.semantic_erase.providers import RegionProviderRegistry


# {
# 責務: [evaluate_candidate: target残存とtarget外pixel driftを評価する]
# 処理: [1: source/output差分をmask外で集計する, 2: boundary continuityを評価する, 3: providerでtarget残存を再検出する]
# 引数: [source: source image, output: candidate image, mask: edited region, target: erase query, registry: detection registry, preservation_mask: original target union]
# 戻り値: [evaluation: candidate quality scores and hard reject result]
# }
def evaluate_candidate(
    source: Image.Image,
    output: Image.Image,
    mask: RLEMask,
    target: SemanticEraseTarget,
    registry: RegionProviderRegistry,
    *,
    preservation_threshold: float = 0.995,
    boundary_threshold: float = 0.20,
    preservation_mask: RLEMask | None = None,
) -> EraseEvaluation:
    source_array = np.asarray(source.convert("RGB"), dtype=np.uint8)
    output_array = np.asarray(output.convert("RGB"), dtype=np.uint8)
    selected = (
        np.frombuffer(mask.to_binary_bytes(), dtype=np.uint8)
        .reshape(mask.height, mask.width)
        .astype(bool)
    )
    preserved_region = selected
    if preservation_mask is not None:
        preserved_region = (
            np.frombuffer(preservation_mask.to_binary_bytes(), dtype=np.uint8)
            .reshape(preservation_mask.height, preservation_mask.width)
            .astype(bool)
        )
    if source_array.shape != output_array.shape or selected.shape != source_array.shape[:2]:
        raise ValueError("candidate image and mask dimensions must match source")
    if preserved_region.shape != selected.shape:
        raise ValueError("preservation mask dimensions must match the source image")
    differences = np.abs(output_array.astype(np.int16) - source_array.astype(np.int16))
    per_pixel_difference = differences.max(axis=2)
    outside = ~preserved_region
    changed_outside = float(np.mean(per_pixel_difference[outside] > 2)) if outside.any() else 0.0
    mean_color_drift = float(np.mean(differences[outside])) / 255 if outside.any() else 0.0
    preservation_score = max(0.0, 1.0 - 0.75 * changed_outside - 0.25 * mean_color_drift)
    boundary_score = _boundary_continuity(output_array, selected)
    residual_candidates = []
    output_rgb = Image.fromarray(output_array)
    providers = registry.providers()
    for _, provider in providers:
        for candidate in provider.propose(output_rgb, target):
            if candidate.mask.width != output.width or candidate.mask.height != output.height:
                continue
            residual_mask = (
                np.frombuffer(candidate.mask.to_binary_bytes(), dtype=np.uint8)
                .reshape(candidate.mask.height, candidate.mask.width)
                .astype(bool)
            )
            overlap = int(np.logical_and(residual_mask, selected).sum())
            residual_area = int(residual_mask.sum())
            # Ignore similarly named objects elsewhere; only an overlapping target is residual.
            if residual_area and overlap / residual_area >= 0.15:
                residual_candidates.append(candidate.confidence)
    residual_score = max(residual_candidates, default=0.0) if providers else None
    reasons = []
    if residual_score is None:
        reasons.append("target_residual_not_verified")
    elif residual_score >= target.confidence_threshold:
        reasons.append("target_may_remain")
    if preservation_score < preservation_threshold:
        reasons.append("non_target_preservation_below_threshold")
    if boundary_score < boundary_threshold:
        reasons.append("boundary_quality_below_threshold")
    return EraseEvaluation(
        residual_score,
        preservation_score,
        boundary_score,
        not reasons,
        tuple(reasons),
    )


# {
# 責務: [_boundary_continuity: mask輪郭上の局所gradient変化を評価する]
# 処理: [1: cross-mask隣接pixel pairを抽出する, 2: output境界gradientから0〜1 scoreを計算する]
# 引数: [output: candidate RGB array, mask: binary edit region]
# 戻り値: [score: boundary continuity score]
# }
def _boundary_continuity(output: np.ndarray, mask: np.ndarray) -> float:
    differences = []
    for axis in (0, 1):
        first = [slice(None), slice(None)]
        second = [slice(None), slice(None)]
        first[axis] = slice(None, -1)
        second[axis] = slice(1, None)
        first_mask = mask[tuple(first)]
        second_mask = mask[tuple(second)]
        crossing = first_mask != second_mask
        if not crossing.any():
            continue
        output_delta = output[tuple(first)].astype(np.int16) - output[tuple(second)].astype(
            np.int16
        )
        boundary_gradient = np.abs(output_delta).mean(axis=2)
        differences.extend(boundary_gradient[crossing].tolist())
    if not differences:
        return 1.0
    return float(np.exp(-np.mean(differences) / 64.0))


# {
# 責務: [make_retry_masks: residual targetに対する局所mask expansionを作る]
# 処理: [1: expanded dilation候補を追加する, 2:既存maskと重複しない候補だけ返す]
# 引数: [mask: original selected mask, retries: retry count]
# 戻り値: [masks: local retry masks]
# }
def make_retry_masks(mask: RLEMask, retries: int = 2) -> tuple[RLEMask, ...]:
    if not 0 <= retries <= 8:
        raise ValueError("retry count must be between 0 and 8")
    source = np.frombuffer(mask.to_binary_bytes(), dtype=np.uint8).reshape(mask.height, mask.width)
    variants = []
    for radius in range(1, retries + 1):
        kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
        expanded = cv2.dilate(source, kernel, iterations=1)
        result = RLEMask.from_binary_bytes(mask.width, mask.height, expanded.tobytes())
        if result not in variants and result.area > mask.area:
            variants.append(result)
    return tuple(variants)
