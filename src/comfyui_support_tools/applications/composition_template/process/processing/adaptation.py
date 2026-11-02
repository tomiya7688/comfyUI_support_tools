"""Aspect-ratio transforms for normalized composition layouts."""

from __future__ import annotations

import math
from dataclasses import replace

from comfyui_support_tools.shared.contracts.composition_template import (
    AspectPolicy,
    CompositionRegion,
    CompositionTemplate,
    HorizonLine,
    VanishingPoint,
    VisualWeightMap,
)


# {
# 責務: [_transform_point: adapt one normalized coordinate to a target canvas]
# 処理: [apply crop, fit, or smart reflow geometry without stretching]
# 引数: [point: source coordinate, source_ratio: source width/height, target_ratio: destination ratio, policy: geometry policy, shift: smart horizontal offset]
# 戻り値: [tuple[float, float] | None: normalized destination point or cropped point]
# }
def _transform_point(
    point: tuple[float, float],
    source_ratio: float,
    target_ratio: float,
    policy: AspectPolicy,
    shift: float,
) -> tuple[float, float] | None:
    x, y = point
    if policy == AspectPolicy.FIT:
        if target_ratio >= source_ratio:
            scale = source_ratio / target_ratio
            return (1 - scale) / 2 + x * scale, y
        scale = target_ratio / source_ratio
        return x, (1 - scale) / 2 + y * scale
    if policy == AspectPolicy.CROP:
        if target_ratio >= source_ratio:
            scale = target_ratio / source_ratio
            return x, (y - 0.5) * scale + 0.5
        scale = source_ratio / target_ratio
        return (x - 0.5) * scale + 0.5, y
    fitted = _transform_point(point, source_ratio, target_ratio, AspectPolicy.FIT, 0.0)
    if fitted is None:
        return None
    return min(1.0, max(0.0, fitted[0] + shift)), fitted[1]


# {
# 責務: [_adapt_region: transform a normalized region and clip it to canvas bounds]
# 処理: [map bbox corners and polygon points through the chosen non-stretch transform]
# 引数: [region: source region, source_ratio: source canvas ratio, target_ratio: destination ratio, policy: adaptation policy, shift: smart reflow offset]
# 戻り値: [CompositionRegion | None: adapted region or fully cropped region]
# }
def _adapt_region(
    region: CompositionRegion,
    source_ratio: float,
    target_ratio: float,
    policy: AspectPolicy,
    shift: float,
) -> CompositionRegion | None:
    x, y, width, height = region.bbox
    corners = [
        _transform_point((x, y), source_ratio, target_ratio, policy, shift),
        _transform_point((x + width, y + height), source_ratio, target_ratio, policy, shift),
    ]
    if any(point is None for point in corners):
        return None
    (x0, y0), (x1, y1) = corners  # type: ignore[misc]
    left, top = max(0.0, min(x0, x1)), max(0.0, min(y0, y1))
    right, bottom = min(1.0, max(x0, x1)), min(1.0, max(y0, y1))
    if right - left < 1e-6 or bottom - top < 1e-6:
        return None
    polygon = tuple(
        point
        for original in region.polygon
        if (point := _transform_point(original, source_ratio, target_ratio, policy, shift))
        is not None
    )
    return replace(region, bbox=(left, top, right - left, bottom - top), polygon=polygon)


# {
# 責務: [_adapt_weight_map: move coarse attention cells with the selected canvas transform]
# 処理: [inverse-map a bounded 8x8 output grid to source saliency cells without stretching]
# 引数: [weight_map: source attention grid, source_ratio: source ratio, target_ratio: destination ratio, policy: transform policy, shift: smart subject offset]
# 戻り値: [VisualWeightMap: adapted attention grid]
# }
def _adapt_weight_map(
    weight_map: VisualWeightMap | None,
    source_ratio: float,
    target_ratio: float,
    policy: AspectPolicy,
    shift: float,
) -> VisualWeightMap | None:
    if weight_map is None:
        return None
    source_rows = weight_map.rows
    row_count, column_count = len(source_rows), len(source_rows[0])
    result: list[tuple[float, ...]] = []
    for row_index in range(row_count):
        values = []
        y = (row_index + 0.5) / row_count
        for column_index in range(column_count):
            x = (column_index + 0.5) / column_count
            if policy in {AspectPolicy.FIT, AspectPolicy.SMART_REFLOW}:
                if target_ratio >= source_ratio:
                    scale = source_ratio / target_ratio
                    source_x = (x - (1 - scale) / 2) / scale
                    source_y = y
                else:
                    scale = target_ratio / source_ratio
                    source_x = x
                    source_y = (y - (1 - scale) / 2) / scale
                if policy == AspectPolicy.SMART_REFLOW:
                    source_x -= shift
            elif target_ratio >= source_ratio:
                scale = target_ratio / source_ratio
                source_x, source_y = x, (y - 0.5) / scale + 0.5
            else:
                scale = source_ratio / target_ratio
                source_x, source_y = (x - 0.5) / scale + 0.5, y
            if not 0 <= source_x <= 1 or not 0 <= source_y <= 1:
                values.append(0.0)
                continue
            source_column = min(column_count - 1, int(source_x * column_count))
            source_row = min(row_count - 1, int(source_y * row_count))
            values.append(source_rows[source_row][source_column])
        result.append(tuple(values))
    return VisualWeightMap(tuple(result))


# {
# 責務: [adapt_template: fit composition evidence to another aspect ratio]
# 処理: [preserve geometry with letterboxing or crop, or shift the subject toward available negative space]
# 引数: [template: source composition, target_ratio: positive width/height ratio, policy: explicit geometry policy]
# 戻り値: [CompositionTemplate: adapted immutable layout]
# }
def adapt_template(
    template: CompositionTemplate, target_ratio: float, policy: AspectPolicy
) -> CompositionTemplate:
    if (
        not isinstance(target_ratio, (int, float))
        or not math.isfinite(target_ratio)
        or target_ratio <= 0
        or target_ratio > 100
    ):
        raise ValueError("target aspect ratio must be a finite positive number no greater than 100")
    if policy == AspectPolicy.SMART_REFLOW and template.subject_regions:
        subject = template.subject_regions[0]
        subject_center = subject.bbox[0] + subject.bbox[2] / 2
        space_centers = [
            region.bbox[0] + region.bbox[2] / 2 for region in template.negative_space_regions
        ]
        if space_centers:
            target_center = max(space_centers, key=lambda value: abs(value - subject_center))
            shift = max(
                -0.2,
                min(0.2, (1 / 3 if target_center > subject_center else 2 / 3) - subject_center),
            )
        else:
            shift = 0.0
    else:
        shift = 0.0
    source_ratio = template.aspect_ratio

    def regions(
        values: tuple[CompositionRegion, ...], horizontal_shift: float = 0.0
    ) -> tuple[CompositionRegion, ...]:
        return tuple(
            adapted
            for region in values
            if (
                adapted := _adapt_region(
                    region, source_ratio, target_ratio, policy, horizontal_shift
                )
            )
            is not None
        )

    horizon = template.horizon
    if (
        horizon
        and policy in {AspectPolicy.FIT, AspectPolicy.SMART_REFLOW}
        and target_ratio < source_ratio
    ):
        scale = target_ratio / source_ratio
        horizon = HorizonLine(
            (1 - scale) / 2 + horizon.y * scale, horizon.angle, horizon.confidence
        )
    vanishing = tuple(
        VanishingPoint(*point, existing.confidence)
        for existing in template.vanishing_points
        if (
            point := _transform_point(
                (existing.x, existing.y),
                source_ratio,
                target_ratio,
                policy,
                0.0 if policy == AspectPolicy.SMART_REFLOW else shift,
            )
        )
        is not None
        and 0 <= point[0] <= 1
        and 0 <= point[1] <= 1
    )
    return replace(
        template,
        aspect_ratio=float(target_ratio),
        subject_regions=regions(template.subject_regions, shift),
        foreground_regions=regions(template.foreground_regions),
        midground_regions=regions(template.midground_regions),
        background_regions=regions(template.background_regions),
        negative_space_regions=regions(template.negative_space_regions),
        salient_regions=regions(template.salient_regions),
        text_safe_regions=regions(template.text_safe_regions),
        optional_panel_layout=regions(template.optional_panel_layout),
        horizon=horizon,
        vanishing_points=vanishing,
        visual_weight_map=_adapt_weight_map(
            template.visual_weight_map, source_ratio, target_ratio, policy, shift
        ),
        reading_flow=tuple(
            point
            for original in template.reading_flow
            if (
                point := _transform_point(
                    original,
                    source_ratio,
                    target_ratio,
                    policy,
                    shift if policy == AspectPolicy.SMART_REFLOW else 0.0,
                )
            )
            is not None
        ),
    )
