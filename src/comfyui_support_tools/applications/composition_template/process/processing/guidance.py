"""Appearance-free prompt and integration guidance exports."""

from __future__ import annotations

import json

from comfyui_support_tools.shared.contracts.composition_template import CompositionTemplate


# {
# 責務: [export_prompt: describe only the spatial composition in generation-friendly language]
# 処理: [format normalized subject, negative-space, framing, and perspective evidence]
# 引数: [template: abstract composition template]
# 戻り値: [str: appearance-free prompt fragment]
# }
def export_prompt(template: CompositionTemplate) -> str:
    main = template.subject_regions[0] if template.subject_regions else None
    parts = [
        f"{template.shot_type.replace('_', ' ')} composition",
        f"canvas aspect ratio {template.aspect_ratio:.3f}",
    ]
    if main:
        x, y, width, height = main.bbox
        horizontal = "left" if x + width / 2 < 0.4 else "right" if x + width / 2 > 0.6 else "center"
        vertical = (
            "upper" if y + height / 2 < 0.4 else "lower" if y + height / 2 > 0.6 else "middle"
        )
        parts.append(
            f"main subject region placed {vertical} {horizontal}, occupying about {width * 100:.0f}% by {height * 100:.0f}% of the frame"
        )
    if template.negative_space_regions:
        space_centers = [
            region.bbox[0] + region.bbox[2] / 2 for region in template.negative_space_regions
        ]
        parts.append(
            "open negative space on the "
            + ("left" if sum(space_centers) / len(space_centers) < 0.45 else "right")
        )
    if template.horizon:
        parts.append(f"horizon near {template.horizon.y * 100:.0f}% of frame height")
    if template.vanishing_points:
        parts.append(
            "perspective lines converge near "
            + ", ".join(
                f"({point.x:.2f}, {point.y:.2f})" for point in template.vanishing_points[:3]
            )
        )
    if template.thirds_alignment:
        parts.append("subject aligned to the rule of thirds")
    return ", ".join(parts) + "."


# {
# 責務: [export_guidance: create a generic generation adapter payload]
# 処理: [serialize normalized geometry, abstraction level and prompt text for downstream consumers]
# 引数: [template: abstract composition template]
# 戻り値: [str: portable JSON guidance document]
# }
def export_guidance(template: CompositionTemplate) -> str:
    payload = {
        "schema": "comfyui-support-tools/composition-guidance/v1",
        "composition_prompt": export_prompt(template),
        "aspect_ratio": template.aspect_ratio,
        "shot_type": template.shot_type,
        "subject_regions": [
            {
                "role": region.role.value,
                "bbox": list(region.bbox),
                "depth_order": region.depth_order,
                "facing_direction": region.facing_direction,
            }
            for region in template.subject_regions
        ],
        "negative_space_regions": [list(region.bbox) for region in template.negative_space_regions],
        "text_safe_regions": [list(region.bbox) for region in template.text_safe_regions],
        "confidence": template.confidence,
        "provenance_warnings": list(template.extraction_provenance.warnings),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
