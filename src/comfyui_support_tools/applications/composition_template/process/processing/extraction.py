"""Heuristic layout extraction with replaceable CV model adapters."""

from __future__ import annotations

import hashlib
import math
from collections import deque
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from comfyui_support_tools.shared.contracts.composition_template import (
    CompositionRegion,
    CompositionTemplate,
    DepthAnalysisAdapter,
    DepthStructure,
    ExtractionLevel,
    ExtractionProvenance,
    HorizonLine,
    PerspectiveAnalysisAdapter,
    PoseAnalysisAdapter,
    RegionRole,
    SubjectAnalysisAdapter,
    VanishingPoint,
    VisualWeightMap,
)

MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_SOURCE_PIXELS = 90_000_000
ANALYSIS_SIZE = 128
GRID_SIZE = 64


# {
# 責務: [_read_source: safely decode one image and compute its provenance hash]
# 処理: [reject links/oversized images, normalize EXIF orientation, bound pixels, and detect concurrent modification]
# 引数: [source: local image path]
# 戻り値: [tuple[Image.Image, str, int, int]: RGB image, SHA-256 and source dimensions]
# エラー: [ValueError: unsupported or unsafe image, RuntimeError: image changes during extraction]
# }
def _read_source(source: str | Path) -> tuple[Image.Image, str, int, int]:
    path = Path(source).expanduser()
    if path.is_symlink():
        raise ValueError("composition source cannot be a symbolic link")
    resolved = path.resolve(strict=True)
    before = resolved.stat()
    if not resolved.is_file() or before.st_size <= 0 or before.st_size > MAX_SOURCE_BYTES:
        raise ValueError("composition source must be a regular image below 128 MiB")
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    try:
        with Image.open(resolved) as decoded:
            decoded.verify()
        with Image.open(resolved) as decoded:
            oriented = ImageOps.exif_transpose(decoded).convert("RGB")
            width, height = oriented.size
            if width < 16 or height < 16 or width * height > MAX_SOURCE_PIXELS:
                raise ValueError("composition image dimensions exceed safe analysis limits")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("composition source is not a safely decodable image") from error
    after = resolved.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("composition source changed during extraction")
    return oriented, digest.hexdigest(), width, height


# {
# 責務: [_saliency_map: estimate composition attention without semantic labels]
# 処理: [combine local contrast, color distance, edge energy and a weak center prior into a normalized 128x128 map]
# 引数: [image: RGB source image]
# 戻り値: [np.ndarray: normalized attention proxy]
# }
def _saliency_map(image: Image.Image) -> np.ndarray:
    analysis = image.resize((ANALYSIS_SIZE, ANALYSIS_SIZE), Image.Resampling.BILINEAR)
    rgb = np.asarray(analysis, dtype=np.float32) / 255.0
    gray_image = analysis.convert("L")
    gray = np.asarray(gray_image, dtype=np.float32) / 255.0
    local = (
        np.asarray(gray_image.filter(ImageFilter.GaussianBlur(radius=4)), dtype=np.float32) / 255.0
    )
    edge = np.asarray(gray_image.filter(ImageFilter.FIND_EDGES), dtype=np.float32) / 255.0
    contrast = np.mean(np.abs(rgb - np.median(rgb, axis=(0, 1))), axis=2)
    local_contrast = np.abs(gray - local)
    height, width = gray.shape
    y, x = np.mgrid[0:height, 0:width]
    center = np.exp(
        -(((x - width / 2) / (width * 0.8)) ** 2 + ((y - height / 2) / (height * 0.8)) ** 2)
    )
    result = (0.45 * contrast + 0.35 * local_contrast + 0.2 * edge) * (0.75 + 0.25 * center)
    low, high = float(result.min()), float(result.max())
    if high - low <= 1e-6:
        return np.zeros_like(result)
    return np.clip((result - low) / (high - low), 0.0, 1.0)


# {
# 責務: [_components: find connected grid regions for saliency bands]
# 処理: [scan a bounded boolean mask with a four-neighbor flood fill]
# 引数: [mask: 2D grid, values: saliency field used to score components]
# 戻り値: [list[tuple[int, int, int, int, float]]: bbox x/y/w/h and component mean score]
# }
def _components(mask: np.ndarray, values: np.ndarray) -> list[tuple[int, int, int, int, float]]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=np.bool_)
    output = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue
            visited[y, x] = True
            pending = deque([(x, y)])
            xs, ys, scores = [], [], []
            while pending:
                cx, cy = pending.popleft()
                xs.append(cx)
                ys.append(cy)
                scores.append(float(values[cy, cx]))
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and mask[ny, nx]
                        and not visited[ny, nx]
                    ):
                        visited[ny, nx] = True
                        pending.append((nx, ny))
            output.append(
                (
                    min(xs),
                    min(ys),
                    max(xs) - min(xs) + 1,
                    max(ys) - min(ys) + 1,
                    sum(scores) / len(scores),
                )
            )
    return output


# {
# 責務: [_region_from_box: create a normalized box region from a grid component]
# 処理: [map grid geometry to 0..1 coordinates and retain only a composition role]
# 引数: [region_id: stable ID, role: composition role, component: grid box/score, grid_width: source grid width, grid_height: source grid height, confidence: measured proxy confidence]
# 戻り値: [CompositionRegion: normalized layout region]
# }
def _region_from_box(
    region_id: str,
    role: RegionRole,
    component: tuple[int, int, int, int, float],
    grid_width: int,
    grid_height: int,
    confidence: float,
) -> CompositionRegion:
    x, y, width, height, score = component
    x0, y0 = x / grid_width, y / grid_height
    x1, y1 = min(1.0, (x + width) / grid_width), min(1.0, (y + height) / grid_height)
    return CompositionRegion(
        region_id,
        role,
        (x0, y0, max(1 / grid_width, x1 - x0), max(1 / grid_height, y1 - y0)),
        relative_scale=math.sqrt(max(0.0, (x1 - x0) * (y1 - y0))),
        attention_weight=max(0.0, min(1.0, score)),
        confidence=max(0.0, min(1.0, confidence)),
    )


# {
# 責務: [_layout_regions: derive approximate subject and negative-space boxes]
# 処理: [extract connected high/low attention components while labeling heuristic evidence as low confidence]
# 引数: [saliency: normalized attention map]
# 戻り値: [tuple[tuple[CompositionRegion, ...], tuple[CompositionRegion, ...], tuple[CompositionRegion, ...]]: subject, negative and salient regions]
# }
def _layout_regions(
    saliency: np.ndarray,
) -> tuple[
    tuple[CompositionRegion, ...], tuple[CompositionRegion, ...], tuple[CompositionRegion, ...]
]:
    small = (
        np.asarray(
            Image.fromarray(np.uint8(saliency * 255)).resize(
                (GRID_SIZE, GRID_SIZE), Image.Resampling.BILINEAR
            ),
            dtype=np.float32,
        )
        / 255.0
    )
    high_threshold = float(np.quantile(small, 0.88))
    high_components = [
        box for box in _components(small >= high_threshold, small) if box[2] * box[3] >= 3
    ]
    high_components.sort(key=lambda box: (box[4] * box[2] * box[3], box[2] * box[3]), reverse=True)
    if high_components:
        subject = _region_from_box(
            "subject-main", RegionRole.MAIN_SUBJECT, high_components[0], GRID_SIZE, GRID_SIZE, 0.42
        )
        subjects = [subject]
        for index, component in enumerate(high_components[1:4], start=1):
            if component[2] * component[3] >= 8:
                subjects.append(
                    _region_from_box(
                        f"subject-support-{index}",
                        RegionRole.SUPPORTING_SUBJECT,
                        component,
                        GRID_SIZE,
                        GRID_SIZE,
                        0.28,
                    )
                )
        salient = tuple(
            _region_from_box(
                f"salient-{index}", RegionRole.SALIENT, component, GRID_SIZE, GRID_SIZE, 0.35
            )
            for index, component in enumerate(high_components[1:5])
        )
    else:
        subjects = [
            CompositionRegion(
                "subject-main", RegionRole.MAIN_SUBJECT, (0.3, 0.2, 0.4, 0.6), confidence=0.08
            )
        ]
        salient = ()
    low_threshold = float(np.quantile(small, 0.35))
    low_components = [
        box for box in _components(small <= low_threshold, 1 - small) if box[2] * box[3] >= 12
    ]
    low_components.sort(key=lambda box: box[2] * box[3], reverse=True)
    negative = tuple(
        _region_from_box(
            f"negative-{index}", RegionRole.EMPTY_SPACE, box, GRID_SIZE, GRID_SIZE, 0.3
        )
        for index, box in enumerate(low_components[:4])
    )
    return tuple(subjects), negative, salient


# {
# 責務: [_visual_weight: compress attention into a portable 8x8 grid]
# 処理: [average each source tile and normalize the resulting values]
# 引数: [saliency: 128x128 normalized attention]
# 戻り値: [VisualWeightMap: coarse attention grid]
# }
def _visual_weight(saliency: np.ndarray) -> VisualWeightMap:
    rows = tuple(
        tuple(
            float(np.mean(saliency[y0:y1, x0:x1]))
            for x0, x1 in zip(
                np.linspace(0, saliency.shape[1], 9, dtype=int)[:-1],
                np.linspace(0, saliency.shape[1], 9, dtype=int)[1:],
                strict=True,
            )
        )
        for y0, y1 in zip(
            np.linspace(0, saliency.shape[0], 9, dtype=int)[:-1],
            np.linspace(0, saliency.shape[0], 9, dtype=int)[1:],
            strict=True,
        )
    )
    high = max((value for row in rows for value in row), default=0.0)
    if high <= 1e-6:
        return VisualWeightMap(tuple(tuple(0.0 for _ in row) for row in rows))
    return VisualWeightMap(tuple(tuple(value / high for value in row) for row in rows))


# {
# 責務: [_reading_flow: identify the strongest coarse attention points]
# 処理: [sort saliency cells by energy and return a few normalized centers]
# 引数: [saliency: normalized attention map]
# 戻り値: [tuple[tuple[float, float], ...]: ordered attention flow points]
# }
def _reading_flow(saliency: np.ndarray) -> tuple[tuple[float, float], ...]:
    small = np.asarray(
        Image.fromarray(np.uint8(saliency * 255)).resize((8, 8), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    peaks = sorted(((float(small[y, x]), x, y) for y in range(8) for x in range(8)), reverse=True)
    selected = []
    for _score, x, y in peaks:
        point = ((x + 0.5) / 8, (y + 0.5) / 8)
        if all(math.dist(point, previous) >= 0.25 for previous in selected):
            selected.append(point)
        if len(selected) == 3:
            break
    return tuple(selected)


# {
# 責務: [_heuristic_horizon: estimate a low-confidence horizontal scene boundary]
# 処理: [rank horizontal gradient energy by row and suppress flat/unstructured images]
# 引数: [image: RGB source image]
# 戻り値: [HorizonLine | None: coarse normalized horizon cue]
# }
def _heuristic_horizon(image: Image.Image) -> HorizonLine | None:
    gray = np.asarray(
        image.resize((ANALYSIS_SIZE, ANALYSIS_SIZE), Image.Resampling.BILINEAR).convert("L"),
        dtype=np.float32,
    )
    vertical_gradient = np.abs(np.gradient(gray, axis=0))
    horizontal_gradient = np.abs(np.gradient(gray, axis=1))
    row_energy = np.mean(vertical_gradient / (1.0 + horizontal_gradient), axis=1)
    if float(row_energy.std()) < 0.01:
        return None
    index = int(np.argmax(row_energy))
    z_score = float((row_energy[index] - row_energy.mean()) / (row_energy.std() + 1e-6))
    if z_score < 1.8 or not 0.15 <= index / ANALYSIS_SIZE <= 0.88:
        return None
    return HorizonLine(index / ANALYSIS_SIZE, confidence=min(0.4, 0.08 * z_score))


# {
# 責務: [_symmetry_score: estimate horizontal balance symmetry]
# 処理: [compare left/right saliency mass on the normalized map]
# 引数: [saliency: normalized visual attention map]
# 戻り値: [float: symmetry proxy in 0..1]
# }
def _symmetry_score(saliency: np.ndarray) -> float:
    half = saliency.shape[1] // 2
    left = saliency[:, :half]
    right = np.fliplr(saliency[:, -half:])
    denominator = float(np.mean(left + right)) + 1e-6
    return max(0.0, min(1.0, 1.0 - float(np.mean(np.abs(left - right))) / denominator))


# {
# 責務: [CompositionExtractionProcessor: build an abstract template from one image]
# フィールド: [no mutable state]
# 処理: [combine a conservative saliency baseline with replaceable detector/pose/depth/perspective adapters]
# }
class CompositionExtractionProcessor:
    # {
    # 責務: [extract: create a resolution-independent composition template]
    # 処理: [inspect source, run optional adapters, classify layout geometry and record provenance/warnings]
    # 引数: [source: local image, level: extraction depth, subject_adapter: optional segmentation/detector, pose_adapter: optional skeleton model, depth_adapter: optional depth model, perspective_adapter: optional horizon/vanishing-point model]
    # 戻り値: [CompositionTemplate: appearance-free normalized layout]
    # }
    def extract(
        self,
        source: str | Path,
        level: ExtractionLevel = ExtractionLevel.LAYOUT,
        subject_adapter: SubjectAnalysisAdapter | None = None,
        pose_adapter: PoseAnalysisAdapter | None = None,
        depth_adapter: DepthAnalysisAdapter | None = None,
        perspective_adapter: PerspectiveAnalysisAdapter | None = None,
    ) -> CompositionTemplate:
        image, image_hash, source_width, source_height = _read_source(source)
        saliency = _saliency_map(image)
        heuristic_subjects, negative, salient = _layout_regions(saliency)
        subject_regions = subject_adapter.analyze(image) if subject_adapter else heuristic_subjects
        if not subject_regions:
            subject_regions = heuristic_subjects
        warnings = (
            [
                "subject boxes use a low-confidence saliency heuristic; no semantic detector was supplied"
            ]
            if subject_adapter is None
            else []
        )
        pose_skeletons = pose_adapter.analyze(image) if pose_adapter else ()
        if pose_adapter is None:
            warnings.append("pose extraction is unavailable because no pose adapter was supplied")
        depth = depth_adapter.analyze(image, subject_regions) if depth_adapter else DepthStructure()
        if not depth.measured:
            warnings.append("relative depth is unmeasured; no depth adapter was supplied")
        if perspective_adapter:
            horizon, vanishing_points = perspective_adapter.analyze(image)
        else:
            horizon, vanishing_points = _heuristic_horizon(image), ()
            warnings.append(
                "vanishing-point estimation is unavailable without a perspective adapter"
            )
        weight_map = _visual_weight(saliency)
        main = next(
            (region for region in subject_regions if region.role == RegionRole.MAIN_SUBJECT),
            subject_regions[0],
        )
        center_x = main.bbox[0] + main.bbox[2] / 2
        center_y = main.bbox[1] + main.bbox[3] / 2
        alignments = []
        for axis, value in (("vertical", center_x), ("horizontal", center_y)):
            if min(abs(value - 1 / 3), abs(value - 2 / 3)) <= 0.12:
                alignments.append(
                    f"{axis}:{'first' if abs(value - 1 / 3) < abs(value - 2 / 3) else 'second'}_third"
                )
        algorithms = ["pillow-saliency-layout-v1", "average-attention-grid-v1"]
        if subject_adapter:
            algorithms.append(type(subject_adapter).__name__)
        if pose_adapter:
            algorithms.append(type(pose_adapter).__name__)
        if depth_adapter:
            algorithms.append(type(depth_adapter).__name__)
        if perspective_adapter:
            algorithms.append(type(perspective_adapter).__name__)
        confidence = min(
            0.45,
            max(0.08, sum(region.confidence for region in subject_regions) / len(subject_regions)),
        )
        return CompositionTemplate(
            aspect_ratio=source_width / source_height,
            shot_type=_shot_type(main),
            camera_angle="unknown",
            horizon=horizon,
            vanishing_points=vanishing_points,
            subject_regions=subject_regions,
            negative_space_regions=negative,
            salient_regions=salient,
            visual_weight_map=weight_map,
            reading_flow=_reading_flow(saliency),
            thirds_alignment=tuple(alignments),
            symmetry=_symmetry_score(saliency),
            pose_skeletons=pose_skeletons,
            depth_structure=depth,
            text_safe_regions=tuple(
                CompositionRegion(
                    f"text-safe-{index}",
                    RegionRole.TEXT_AREA,
                    region.bbox,
                    region.polygon,
                    region.relative_scale,
                    region.depth_order,
                    attention_weight=1.0 - region.attention_weight,
                    confidence=region.confidence,
                )
                for index, region in enumerate(negative[:2])
            ),
            confidence=confidence,
            extraction_provenance=ExtractionProvenance(
                image_hash,
                source_width,
                source_height,
                level,
                tuple(algorithms),
                tuple(warnings),
            ),
        )


# {
# 責務: [_shot_type: classify rough framing scale from a normalized region]
# 処理: [map relative subject extent to close-up, bust, full-body, or wide-shot labels]
# 引数: [subject: main normalized composition region]
# 戻り値: [str: coarse framing label]
# }
def _shot_type(subject: CompositionRegion) -> str:
    _, _, width, height = subject.bbox
    if width >= 0.72 and height <= 0.48:
        return "wide_shot"
    if height >= 0.72:
        return "full_body"
    if height >= 0.42:
        return "bust"
    return "close_up"
