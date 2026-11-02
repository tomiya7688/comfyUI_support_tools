"""Versioned JSON conversion for composition templates."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from comfyui_support_tools.shared.contracts.composition_template import (
    CompositionRegion,
    CompositionTemplate,
    DepthLayer,
    DepthStructure,
    ExtractionLevel,
    ExtractionProvenance,
    HorizonLine,
    PoseKeypoint,
    PoseSkeleton,
    RegionRole,
    VanishingPoint,
    VisualWeightMap,
)

MAX_TEMPLATE_BYTES = 2 * 1024 * 1024


# {
# 責務: [_encode: convert immutable contract values into JSON-compatible values]
# 処理: [recursively encode dataclasses, enums, tuples, and primitive values]
# 引数: [value: contract value]
# 戻り値: [object: JSON-compatible representation]
# }
def _encode(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


# {
# 責務: [template_to_json: export a template using stable versioned JSON]
# 処理: [serialize the appearance-free contract as compact UTF-8 JSON]
# 引数: [template: validated composition template]
# 戻り値: [str: JSON document]
# }
def template_to_json(template: CompositionTemplate) -> str:
    return json.dumps(_encode(template), ensure_ascii=False, indent=2, allow_nan=False) + "\n"


# {
# 責務: [_require_keys: constrain untrusted object fields to an expected schema]
# 処理: [reject missing and unknown keys before constructing contract values]
# 引数: [value: object, expected: tuple[str, ...], path: error location]
# 戻り値: [dict[str, Any]: validated mapping]
# }
def _require_keys(value: object, expected: tuple[str, ...], path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{path} has missing or unsupported fields")
    return value


# {
# 責務: [_unique_object: reject duplicate keys in an untrusted JSON object]
# 処理: [build a dict only when every key occurs exactly once]
# 引数: [pairs: parsed JSON key/value pairs]
# 戻り値: [dict[str, Any]: unique object mapping]
# }
def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


# {
# 責務: [template_from_json: validate and load a versioned composition template]
# 処理: [bound input size, reject duplicate/nonstandard JSON constants, and instantiate validated contracts]
# 引数: [document: JSON text]
# 戻り値: [CompositionTemplate: validated template]
# }
def template_from_json(document: str) -> CompositionTemplate:
    if not isinstance(document, str) or len(document.encode("utf-8")) > MAX_TEMPLATE_BYTES:
        raise ValueError("template JSON exceeds the 2 MiB limit")

    # {
    # 責務: [reject_constant: reject non-standard JSON numeric constants]
    # 処理: [raise a structured input error for NaN and Infinity tokens]
    # 引数: [constant: JSON constant token]
    # 戻り値: [None: always raises ValueError]
    # }
    def reject_constant(constant: str) -> None:
        raise ValueError(f"unsupported JSON number: {constant}")

    try:
        raw = json.loads(document, parse_constant=reject_constant, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError("template JSON is malformed") from error
    root_keys = (
        "aspect_ratio",
        "shot_type",
        "camera_angle",
        "subject_regions",
        "confidence",
        "extraction_provenance",
        "horizon",
        "vanishing_points",
        "foreground_regions",
        "midground_regions",
        "background_regions",
        "negative_space_regions",
        "salient_regions",
        "visual_weight_map",
        "reading_flow",
        "thirds_alignment",
        "symmetry",
        "diagonal_flow",
        "pose_skeletons",
        "facing_directions",
        "depth_structure",
        "text_safe_regions",
        "optional_panel_layout",
        "schema_version",
    )
    root = _require_keys(raw, root_keys, "template")
    list_fields = (
        "subject_regions",
        "vanishing_points",
        "foreground_regions",
        "midground_regions",
        "background_regions",
        "negative_space_regions",
        "salient_regions",
        "reading_flow",
        "thirds_alignment",
        "pose_skeletons",
        "facing_directions",
        "text_safe_regions",
        "optional_panel_layout",
    )
    for field_name in list_fields:
        if not isinstance(root[field_name], list) or len(root[field_name]) > 512:
            raise ValueError(f"{field_name} must be an array with at most 512 entries")

    # {
    # 責務: [point: decode one normalized coordinate pair]
    # 処理: [require exactly two numeric coordinates]
    # 引数: [value: JSON coordinate value]
    # 戻り値: [tuple[float, float]: decoded coordinate]
    # }
    def point(value: object) -> tuple[float, float]:
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("point must contain two coordinates")
        return float(value[0]), float(value[1])

    # {
    # 責務: [region: decode one validated composition region]
    # 処理: [require the exact region schema and instantiate normalized geometry]
    # 引数: [value: JSON region value]
    # 戻り値: [CompositionRegion: validated region]
    # }
    def region(value: object) -> CompositionRegion:
        item = _require_keys(
            value,
            (
                "id",
                "role",
                "bbox",
                "polygon",
                "relative_scale",
                "depth_order",
                "facing_direction",
                "attention_weight",
                "confidence",
            ),
            "region",
        )
        return CompositionRegion(
            str(item["id"]),
            RegionRole(item["role"]),
            tuple(float(v) for v in item["bbox"]),
            tuple(point(v) for v in item["polygon"]),
            float(item["relative_scale"]),
            item["depth_order"],
            item["facing_direction"],
            float(item["attention_weight"]),
            float(item["confidence"]),
        )

    # {
    # 責務: [regions: decode one region collection]
    # 処理: [require a JSON array and validate each region]
    # 引数: [name: root field name]
    # 戻り値: [tuple[CompositionRegion, ...]: validated regions]
    # }
    def regions(name: str) -> tuple[CompositionRegion, ...]:
        if not isinstance(root[name], list):
            raise ValueError(f"{name} must be a list")
        return tuple(region(value) for value in root[name])

    source = _require_keys(
        root["extraction_provenance"],
        (
            "image_sha256",
            "source_width",
            "source_height",
            "extraction_level",
            "algorithms",
            "warnings",
        ),
        "provenance",
    )
    provenance = ExtractionProvenance(
        str(source["image_sha256"]),
        int(source["source_width"]),
        int(source["source_height"]),
        ExtractionLevel(source["extraction_level"]),
        tuple(str(v) for v in source["algorithms"]),
        tuple(str(v) for v in source["warnings"]),
    )
    horizon = None
    if root["horizon"] is not None:
        item = _require_keys(root["horizon"], ("y", "angle", "confidence"), "horizon")
        horizon = HorizonLine(float(item["y"]), float(item["angle"]), float(item["confidence"]))
    vanishing_points = tuple(
        VanishingPoint(float(item["x"]), float(item["y"]), float(item["confidence"]))
        for item in root["vanishing_points"]
    )
    weight = None
    if root["visual_weight_map"] is not None:
        item = _require_keys(root["visual_weight_map"], ("rows",), "visual weight map")
        weight = VisualWeightMap(
            tuple(tuple(float(value) for value in row) for row in item["rows"])
        )
    skeletons = []
    for skeleton_value in root["pose_skeletons"]:
        item = _require_keys(skeleton_value, ("id", "keypoints", "confidence"), "pose skeleton")
        keypoints = tuple(
            PoseKeypoint(str(key["name"]), point(key["point"]), float(key["visibility"]))
            for key in item["keypoints"]
        )
        skeletons.append(PoseSkeleton(str(item["id"]), keypoints, float(item["confidence"])))
    depth_value = _require_keys(
        root["depth_structure"], ("layers", "confidence", "measured"), "depth"
    )
    if not isinstance(depth_value["measured"], bool):
        raise ValueError("depth measured flag must be a JSON boolean")
    if not isinstance(depth_value["layers"], list) or len(depth_value["layers"]) > 512:
        raise ValueError("depth layers must be an array with at most 512 entries")
    depth_layers = tuple(
        DepthLayer(
            int(item["order"]), tuple(str(v) for v in item["region_ids"]), float(item["confidence"])
        )
        for item in depth_value["layers"]
    )
    depth = DepthStructure(
        depth_layers, float(depth_value["confidence"]), bool(depth_value["measured"])
    )
    return CompositionTemplate(
        aspect_ratio=float(root["aspect_ratio"]),
        shot_type=str(root["shot_type"]),
        camera_angle=str(root["camera_angle"]),
        subject_regions=regions("subject_regions"),
        confidence=float(root["confidence"]),
        extraction_provenance=provenance,
        horizon=horizon,
        vanishing_points=vanishing_points,
        foreground_regions=regions("foreground_regions"),
        midground_regions=regions("midground_regions"),
        background_regions=regions("background_regions"),
        negative_space_regions=regions("negative_space_regions"),
        salient_regions=regions("salient_regions"),
        visual_weight_map=weight,
        reading_flow=tuple(point(value) for value in root["reading_flow"]),
        thirds_alignment=tuple(str(value) for value in root["thirds_alignment"]),
        symmetry=None if root["symmetry"] is None else float(root["symmetry"]),
        diagonal_flow=None if root["diagonal_flow"] is None else float(root["diagonal_flow"]),
        pose_skeletons=tuple(skeletons),
        facing_directions=tuple(tuple(str(v) for v in item) for item in root["facing_directions"]),
        depth_structure=depth,
        text_safe_regions=regions("text_safe_regions"),
        optional_panel_layout=regions("optional_panel_layout"),
        schema_version=int(root["schema_version"]),
    )
