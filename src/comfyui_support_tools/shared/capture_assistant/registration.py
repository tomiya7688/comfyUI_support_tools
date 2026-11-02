"""Registration and confidence-weighted fusion for short burst sequences."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from PIL import Image


# {
#   責務: [FrameRegistrationEvidence: one frameの位置合わせと画質根拠を保持する]
#   フィールド: [source, quality, transform, confidence, visibility, residual, accepted]
# }
@dataclass(frozen=True, slots=True)
class FrameRegistrationEvidence:
    source: str
    quality: float
    registration_method: str
    registration_confidence: float
    inlier_ratio: float
    visible_fraction: float
    photometric_residual: float
    ghosting_fraction: float
    accepted: bool
    warnings: tuple[str, ...] = ()


# {
#   責務: [BurstFusionResult: fused observationとsafe fallback候補を保持する]
#   フィールド: [fused image, best frame, confidence maps, evidence, provenance]
# }
@dataclass(frozen=True, slots=True)
class BurstFusionResult:
    fused_png: bytes | None
    best_frame_png: bytes
    source_paths: tuple[str, ...]
    frame_evidence: tuple[FrameRegistrationEvidence, ...]
    confidence_map_png: bytes
    observation_count_map_png: bytes
    edge_support_map_png: bytes
    texture_support_map_png: bytes
    generator: str = "orb_ecc_flow_confidence_fusion_v1"
    warnings: tuple[str, ...] = ()
    super_resolution_png: bytes | None = None
    super_resolution_backend: str = ""

    # {
    #   責務: [candidate_images: fused、best-frame、optional SR候補を返す]
    #   処理: [preserve separate evidence provenance for each candidate]
    #   引数: [self: completed burst assessment]
    #   戻り値: [tuple[tuple[str, bytes, str], ...]: label, payload, provenance]
    # }
    def candidate_images(self) -> tuple[tuple[str, bytes, str], ...]:
        candidates = [("best_single_frame", self.best_frame_png, "observed_best_quality_frame")]
        if self.fused_png is not None:
            candidates.append(("multi_frame_fusion", self.fused_png, self.generator))
        if self.super_resolution_png is not None:
            candidates.append(
                (
                    "multi_frame_super_resolution",
                    self.super_resolution_png,
                    self.super_resolution_backend,
                )
            )
        return tuple(candidates)


# {
#   責務: [BurstSuperResolutionBackend: optional multi-frame SRを注入するprotocol]
#   フィールド: [name, upscale]
#   処理: [receive fused observation and confidence map as explicit evidence]
# }
class BurstSuperResolutionBackend(Protocol):
    # {
    #   責務: [name: SR backend provenanceを返す]
    #   処理: [identify optional generator in candidate reports]
    #   引数: [self: injected super-resolution adapter]
    #   戻り値: [str: stable backend identifier]
    # }
    @property
    def name(self) -> str: ...

    # {
    #   責務: [upscale: fused evidenceをoptional SR候補へ変換する]
    #   処理: [receive source fusion and per-pixel confidence separately]
    #   引数: [fused_png: fused pixels, confidence_map_png: evidence confidence]
    #   戻り値: [bytes: encoded SR candidate]
    # }
    def upscale(self, fused_png: bytes, confidence_map_png: bytes) -> bytes: ...


# {
#   責務: [register_and_fuse_burst: quality付きburstをglobal/local alignmentしてevidence fusionする]
#   処理: [ORB/RANSAC, ECC or phase-correlation registration; optional dense flow; robust confidence weighting]
#   引数: [images: decoded observations, source_paths: provenance names, quality_scores: per-frame quality, frame_range: optional half-open range, super_resolution: optional plugin]
#   戻り値: [BurstFusionResult: fused candidate or explicit best-frame fallback]
#   エラー: [ValueError: invalid range, mismatched input, or resource limit]
# }
def register_and_fuse_burst(
    images: tuple[Image.Image, ...],
    source_paths: tuple[str, ...],
    quality_scores: tuple[float, ...],
    frame_range: tuple[int, int] | None = None,
    super_resolution: BurstSuperResolutionBackend | None = None,
) -> BurstFusionResult:
    if len(images) < 2 or len(images) != len(source_paths) or len(images) != len(quality_scores):
        raise ValueError("burst fusion requires matching image, source, and quality sequences")
    start, end = frame_range or (0, len(images))
    if start < 0 or end > len(images) or end - start < 2:
        raise ValueError("frame_range must select at least two available frames")
    images = images[start:end]
    source_paths = source_paths[start:end]
    quality_scores = quality_scores[start:end]
    if any(not 0 <= score <= 1 or not math.isfinite(score) for score in quality_scores):
        raise ValueError("frame quality scores must be finite and normalized")
    try:
        import cv2
    except ImportError:
        return _fallback_result(images, source_paths, quality_scores, "opencv_unavailable")
    reference_index = max(range(len(images)), key=quality_scores.__getitem__)
    reference = np.asarray(images[reference_index].convert("RGB"), dtype=np.uint8)
    height, width = reference.shape[:2]
    if height * width > 4_000_000 or len(images) > 12:
        raise ValueError("burst fusion is limited to 12 frames and 4 megapixels")
    reference_gray = cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)
    registered: list[np.ndarray | None] = []
    confidences: list[np.ndarray | None] = []
    evidence: list[FrameRegistrationEvidence] = []
    warnings: list[str] = []
    orb = cv2.ORB_create(nfeatures=3000, scaleFactor=1.2, nlevels=8)
    reference_keypoints, reference_descriptors = orb.detectAndCompute(reference_gray, None)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    for index, (image, source, quality) in enumerate(
        zip(images, source_paths, quality_scores, strict=True)
    ):
        current = np.asarray(image.convert("RGB").resize((width, height)), dtype=np.uint8)
        if index == reference_index:
            aligned = current
            method, alignment_confidence, inlier_ratio, registration_warning = (
                "reference",
                1.0,
                1.0,
                (),
            )
        else:
            aligned, method, alignment_confidence, inlier_ratio, registration_warning = (
                _align_frame(
                    current,
                    reference_gray,
                    reference_keypoints,
                    reference_descriptors,
                    orb,
                    matcher,
                    cv2,
                )
            )
        if aligned is None:
            registered.append(None)
            confidences.append(None)
            evidence.append(
                FrameRegistrationEvidence(
                    source,
                    quality,
                    method,
                    0.0,
                    inlier_ratio,
                    0.0,
                    1.0,
                    1.0,
                    False,
                    registration_warning,
                )
            )
            continue
        warped, flow_confidence, visible = _local_align_and_confidence(reference_gray, aligned, cv2)
        gray = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
        residual_image = cv2.absdiff(reference_gray, gray).astype(np.float32) / 255
        residual = float(np.mean(residual_image))
        global_residual = (
            cv2.absdiff(reference_gray, cv2.cvtColor(aligned, cv2.COLOR_RGB2GRAY)).astype(
                np.float32
            )
            / 255
        )
        ghosting_fraction = float(np.mean((global_residual > 0.20) & (visible > 0)))
        residual_confidence = math.exp(-residual * 5.0)
        frame_confidence = np.clip(
            flow_confidence * alignment_confidence * residual_confidence * quality, 0, 1
        )
        accepted = bool(
            np.mean(frame_confidence) >= 0.025
            and np.mean(visible) >= 0.25
            and ghosting_fraction < 0.40
        )
        notes = tuple(registration_warning)
        if ghosting_fraction >= 0.05:
            notes += ("ghosting_risk",)
        if ghosting_fraction >= 0.25:
            notes += ("major_ghosting_risk",)
        if not accepted:
            notes += ("alignment_or_ghosting_confidence_too_low",)
        registered.append(warped if accepted else None)
        confidences.append(frame_confidence if accepted else None)
        evidence.append(
            FrameRegistrationEvidence(
                source,
                quality,
                method,
                float(alignment_confidence),
                float(inlier_ratio),
                float(np.mean(visible)),
                residual,
                ghosting_fraction,
                accepted,
                notes,
            )
        )
        warnings.extend(notes)
    usable = [index for index, frame in enumerate(registered) if frame is not None]
    if len(usable) < 2:
        return _fallback_result(
            images,
            source_paths,
            quality_scores,
            "insufficient_confident_alignment",
            tuple(evidence),
        )
    fused, confidence_map, count_map, edge_map, texture_map = _robust_weighted_fusion(
        registered, confidences, usable, cv2
    )
    fused_png = _png_bytes(fused)
    confidence_png = _gray_png(confidence_map * 255)
    count_png = _gray_png(count_map)
    super_resolution_png = None
    backend_name = ""
    if super_resolution is not None:
        try:
            super_resolution_png = super_resolution.upscale(fused_png, confidence_png)
            backend_name = super_resolution.name
        except Exception as error:
            warnings.append(f"super_resolution_failed:{type(error).__name__}")
    return BurstFusionResult(
        fused_png,
        _png_bytes(np.asarray(images[reference_index].convert("RGB"), dtype=np.uint8)),
        tuple(source_paths),
        tuple(evidence),
        confidence_png,
        count_png,
        _gray_png(edge_map * 255),
        _gray_png(texture_map * 255),
        warnings=tuple(dict.fromkeys(warnings)),
        super_resolution_png=super_resolution_png,
        super_resolution_backend=backend_name,
    )


# {
#   責務: [_align_frame: reference imageへglobal transformを適用する]
#   処理: [feature RANSAC first, ECC affine second, phase correlation last; reject weak estimates]
#   引数: [frame: input RGB, reference_gray: target, feature data, OpenCV module]
#   戻り値: [aligned RGB or None, method, confidence, inlier ratio, warnings]
# }
def _align_frame(
    frame, reference_gray, reference_keypoints, reference_descriptors, orb, matcher, cv2
):
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    if float(np.std(gray)) < 2 or float(np.std(reference_gray)) < 2:
        return None, "rejected_low_texture", 0.0, 0.0, ("insufficient_registration_texture",)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    if descriptors is not None and reference_descriptors is not None:
        pairs = matcher.knnMatch(descriptors, reference_descriptors, k=2)
        good = [first for first, second in pairs if first.distance < 0.72 * second.distance]
        if len(good) >= 8:
            source = np.float32([keypoints[item.queryIdx].pt for item in good]).reshape(-1, 1, 2)
            target = np.float32([reference_keypoints[item.trainIdx].pt for item in good]).reshape(
                -1, 1, 2
            )
            transform, mask = cv2.findHomography(source, target, cv2.RANSAC, 3.0)
            ratio = float(np.mean(mask)) if mask is not None else 0.0
            if transform is not None and np.isfinite(transform).all() and ratio >= 0.15:
                aligned = cv2.warpPerspective(frame, transform, (frame.shape[1], frame.shape[0]))
                return aligned, "orb_ransac_homography", min(1.0, ratio * 1.5), ratio, ()
    warp = np.eye(2, 3, dtype=np.float32)
    try:
        score, warp = cv2.findTransformECC(
            reference_gray,
            gray,
            warp,
            cv2.MOTION_AFFINE,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5),
            None,
            3,
        )
        if score >= 0.45:
            aligned = cv2.warpAffine(
                frame,
                warp,
                (frame.shape[1], frame.shape[0]),
                flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
            )
            return aligned, "ecc_affine", float(np.clip(score, 0, 1)), 0.0, ()
    except cv2.error:
        pass
    shift, response = cv2.phaseCorrelate(reference_gray.astype(np.float32), gray.astype(np.float32))
    if response >= 0.25 and math.hypot(*shift) < min(frame.shape[:2]) * 0.35:
        matrix = np.float32([[1, 0, -shift[0]], [0, 1, -shift[1]]])
        aligned = cv2.warpAffine(frame, matrix, (frame.shape[1], frame.shape[0]))
        return (
            aligned,
            "phase_correlation_translation",
            float(np.clip(response, 0, 0.8)),
            0.0,
            ("translation_only_alignment",),
        )
    return None, "rejected", 0.0, 0.0, ("global_registration_failed",)


# {
#   責務: [_local_align_and_confidence: optical flowでlocal registrationと可視性を推定する]
#   処理: [warp aligned evidence into reference coordinates and penalize photometric disagreement]
#   引数: [reference_gray: target, aligned_rgb: globally registered frame, cv2: OpenCV]
#   戻り値: [warped RGB, pixel confidence, visibility mask]
# }
def _local_align_and_confidence(reference_gray, aligned_rgb, cv2):
    height, width = reference_gray.shape
    aligned_gray = cv2.cvtColor(aligned_rgb, cv2.COLOR_RGB2GRAY)
    flow = cv2.calcOpticalFlowFarneback(
        reference_gray, aligned_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
    )
    grid_x, grid_y = np.meshgrid(np.arange(width), np.arange(height))
    map_x = grid_x.astype(np.float32) + flow[..., 0]
    map_y = grid_y.astype(np.float32) + flow[..., 1]
    visible = (map_x >= 0) & (map_x < width - 1) & (map_y >= 0) & (map_y < height - 1)
    warped = cv2.remap(aligned_rgb, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)
    residual = cv2.absdiff(reference_gray, warped_gray).astype(np.float32) / 255
    flow_size = cv2.magnitude(flow[..., 0], flow[..., 1])
    motion_penalty = np.exp(-np.maximum(flow_size - 12, 0) / 10)
    confidence = np.exp(-residual * 6) * motion_penalty * visible.astype(np.float32)
    return warped, confidence, visible.astype(np.float32)


# {
#   責務: [_robust_weighted_fusion: pixel-wise confidence and temporal consensusからobservationを作る]
#   処理: [quality/confidence weighted mean with robust residual downweighting and evidence maps]
#   引数: [registered frames, confidence maps, usable indices]
#   戻り値: [fused RGB, confidence map, observation count map]
# }
def _robust_weighted_fusion(registered, confidences, usable, cv2):
    reference = registered[usable[0]].astype(np.float32)
    height, width = reference.shape[:2]
    total = np.zeros((height, width), dtype=np.float32)
    accum = np.zeros_like(reference, dtype=np.float32)
    for index in usable:
        weight = confidences[index]
        total += weight
        accum += registered[index].astype(np.float32) * weight[..., None]
    initial = accum / np.maximum(total[..., None], 1e-5)
    robust_total = np.zeros_like(total)
    robust_accum = np.zeros_like(accum)
    count = np.zeros_like(total)
    edge_accum = np.zeros_like(total)
    texture_accum = np.zeros_like(total)
    for index in usable:
        pixels = registered[index].astype(np.float32)
        residual = np.mean(np.abs(pixels - initial), axis=2)
        robust = 1 / (1 + (residual / 18) ** 2)
        weight = confidences[index] * robust
        robust_total += weight
        robust_accum += pixels * weight[..., None]
        count += (weight > 0.08).astype(np.float32)
        gray = cv2.cvtColor(registered[index], cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(gray, 80, 160).astype(np.float32) / 255
        local_mean = cv2.blur(gray.astype(np.float32), (5, 5))
        local_square_mean = cv2.blur(gray.astype(np.float32) ** 2, (5, 5))
        texture = np.sqrt(np.maximum(local_square_mean - local_mean**2, 0))
        texture = np.clip(texture / 48, 0, 1)
        edge_accum += edges * weight
        texture_accum += texture * weight
    fused = np.clip(robust_accum / np.maximum(robust_total[..., None], 1e-5), 0, 255).astype(
        np.uint8
    )
    confidence = np.clip(robust_total / max(len(usable), 1), 0, 1)
    edge_support = edge_accum / np.maximum(robust_total, 1e-5)
    texture_support = texture_accum / np.maximum(robust_total, 1e-5)
    return (
        fused,
        confidence,
        np.clip(count / max(len(usable), 1) * 255, 0, 255),
        np.clip(edge_support, 0, 1),
        np.clip(texture_support, 0, 1),
    )


# {
#   責務: [_fallback_result: alignmentが不確かな場合にbest originalを候補として返す]
#   処理: [never synthesize a fused image from unregistered evidence]
#   引数: [images, paths, quality, fallback reason, optional evidence]
#   戻り値: [BurstFusionResult: fused image omitted and original preserved]
# }
def _fallback_result(images, paths, quality, reason, evidence=()):
    best = max(range(len(quality)), key=quality.__getitem__)
    image = np.asarray(images[best].convert("RGB"), dtype=np.uint8)
    blank = np.zeros(image.shape[:2], dtype=np.uint8)
    entries = tuple(evidence) or tuple(
        FrameRegistrationEvidence(
            path, score, "not_aligned", 0.0, 0.0, 0.0, 1.0, 1.0, False, (reason,)
        )
        for path, score in zip(paths, quality, strict=True)
    )
    return BurstFusionResult(
        None,
        _png_bytes(image),
        tuple(paths),
        entries,
        _gray_png(blank),
        _gray_png(blank),
        _gray_png(blank),
        _gray_png(blank),
        warnings=(reason,),
    )


# {
#   責務: [_png_bytes: RGB arrayをPNGへencodeする]
#   処理: [serialize fused pixels deterministically]
#   引数: [rgb: uint8 image]
#   戻り値: [bytes: PNG payload]
# }
def _png_bytes(rgb):
    stream = io.BytesIO()
    Image.fromarray(np.asarray(rgb, dtype=np.uint8), "RGB").save(
        stream, format="PNG", optimize=True
    )
    return stream.getvalue()


# {
#   責務: [_gray_png: scalar evidence mapをPNGへencodeする]
#   処理: [normalize confidence/count maps to uint8]
#   引数: [array: normalized confidence or count]
#   戻り値: [bytes: L-mode PNG]
# }
def _gray_png(array):
    stream = io.BytesIO()
    Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), "L").save(
        stream, format="PNG", optimize=True
    )
    return stream.getvalue()
