"""Sparse user guidance contracts and conservative image-space priors."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

_POINT_LABELS = {"surface", "hidden_object", "background", "edge", "color_sample"}
_STROKE_LABELS = {"surface", "hidden_object", "exclude", "contour"}
_CATEGORIES = {"", "generic", "clothing", "cloth", "shirt", "skin", "paper", "film", "other"}
_MATERIALS = {"", "cloth", "thin_cloth", "thick_cloth", "paper", "plastic", "glass", "other"}


# {
#   責務: [GuidancePoint: normalized point hint and confidenceを保持する]
#   フィールド: [x, y, label, confidence, expected_rgb]
# }
@dataclass(frozen=True, slots=True)
class GuidancePoint:
    x: float
    y: float
    label: str
    confidence: float = 0.7
    expected_rgb: tuple[int, int, int] | None = None

    # {
    #   責務: [__post_init__: normalized location and semantic hintをvalidateする]
    #   処理: [reject unsupported label, coordinate, confidence, and RGB values]
    #   引数: [self: one sparse user constraint]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        _validate_unit(self.x, "x")
        _validate_unit(self.y, "y")
        _validate_unit(self.confidence, "confidence")
        if self.label not in _POINT_LABELS:
            raise ValueError("unsupported guidance point label")
        if self.label == "color_sample" and self.expected_rgb is None:
            raise ValueError("color_sample points require an expected RGB value")
        if self.expected_rgb is not None and (
            not isinstance(self.expected_rgb, tuple)
            or len(self.expected_rgb) != 3
            or any(
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255
                for value in self.expected_rgb
            )
        ):
            raise ValueError("expected_rgb must contain three byte channel values")


# {
#   責務: [GuidanceScribble: normalized freehand constraintを保持する]
#   フィールド: [points, label, width, confidence]
# }
@dataclass(frozen=True, slots=True)
class GuidanceScribble:
    points: tuple[tuple[float, float], ...]
    label: str
    width: float = 0.025
    confidence: float = 0.7

    # {
    #   責務: [__post_init__: stroke path, width, and confidenceをvalidateする]
    #   処理: [bound normalized points and supported stroke labels]
    #   引数: [self: one rasterizable user stroke]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.points, tuple) or len(self.points) < 1 or len(self.points) > 10000:
            raise ValueError("scribble requires an immutable tuple of 1 to 10000 points")
        if self.label not in _STROKE_LABELS:
            raise ValueError("unsupported guidance scribble label")
        _validate_unit(self.width, "width")
        if self.width == 0:
            raise ValueError("scribble width must be positive")
        _validate_unit(self.confidence, "confidence")
        for x, y in self.points:
            _validate_unit(x, "x")
            _validate_unit(y, "y")


# {
#   責務: [GuidanceHints: sparse points/strokes/category/material priorsを共通contract化する]
#   フィールド: [points, scribbles, category, material, confidence, schema]
# }
@dataclass(frozen=True, slots=True)
class GuidanceHints:
    points: tuple[GuidancePoint, ...] = ()
    scribbles: tuple[GuidanceScribble, ...] = ()
    category: str = ""
    material: str = ""
    confidence: float = 0.7
    source_sha256: str = ""
    schema: str = "guidance-hints.v1"

    # {
    #   責務: [__post_init__: hint count, category and confidenceをvalidateする]
    #   処理: [allow hint-free automatic processing and cap excessive annotation density]
    #   引数: [self: optional set of user constraints]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if self.schema != "guidance-hints.v1":
            raise ValueError("unsupported guidance hint schema")
        if not isinstance(self.points, tuple) or not isinstance(self.scribbles, tuple):
            raise TypeError("guidance points and scribbles must be immutable tuples")
        if len(self.points) > 128 or len(self.scribbles) > 128:
            raise ValueError("guidance hint limits exceeded")
        if self.category not in _CATEGORIES or self.material not in _MATERIALS:
            raise ValueError("unsupported semantic category or material")
        _validate_unit(self.confidence, "confidence")
        if self.source_sha256 and not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256 hex digest")
        if any(not isinstance(point, GuidancePoint) for point in self.points):
            raise TypeError("points must contain GuidancePoint values")
        if any(not isinstance(stroke, GuidanceScribble) for stroke in self.scribbles):
            raise TypeError("scribbles must contain GuidanceScribble values")

    # {
    #   責務: [to_dict: guidance contractをversioned JSON-compatible objectへ変換する]
    #   処理: [serialize normalized points and strokes without image pixel data]
    #   引数: [self: immutable user hints]
    #   戻り値: [dict[str, object]: guidance-hints.v1 object]
    # }
    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "category": self.category,
            "material": self.material,
            "confidence": self.confidence,
            "source_sha256": self.source_sha256,
            "points": [
                {
                    "x": point.x,
                    "y": point.y,
                    "label": point.label,
                    "confidence": point.confidence,
                    "expected_rgb": point.expected_rgb,
                }
                for point in self.points
            ],
            "scribbles": [
                {
                    "points": stroke.points,
                    "label": stroke.label,
                    "width": stroke.width,
                    "confidence": stroke.confidence,
                }
                for stroke in self.scribbles
            ],
        }

    # {
    #   責務: [from_dict: untrusted JSON-compatible valueをvalidated contractへ復元する]
    #   処理: [reject malformed arrays, labels, points, and unexpected field types]
    #   引数: [value: parsed guidance JSON object]
    #   戻り値: [GuidanceHints: validated sparse hint data]
    # }
    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> GuidanceHints:
        if not isinstance(value, dict) or value.get("schema") != "guidance-hints.v1":
            raise ValueError("guidance file schema must be guidance-hints.v1")
        raw_points = value.get("points", [])
        raw_strokes = value.get("scribbles", [])
        if not isinstance(raw_points, list) or not isinstance(raw_strokes, list):
            raise ValueError("guidance points and scribbles must be arrays")
        points = tuple(
            GuidancePoint(
                _number(row, "x"),
                _number(row, "y"),
                _string(row, "label"),
                _number(row, "confidence", 0.7),
                tuple(row["expected_rgb"]) if row.get("expected_rgb") is not None else None,
            )
            for row in raw_points
            if isinstance(row, dict)
        )
        if len(points) != len(raw_points):
            raise ValueError("each guidance point must be an object")
        strokes = tuple(
            GuidanceScribble(
                tuple(tuple(_number_pair(pair)) for pair in row.get("points", [])),
                _string(row, "label"),
                _number(row, "width", 0.025),
                _number(row, "confidence", 0.7),
            )
            for row in raw_strokes
            if isinstance(row, dict)
        )
        if len(strokes) != len(raw_strokes):
            raise ValueError("each guidance scribble must be an object")
        return cls(
            points,
            strokes,
            _string(value, "category", ""),
            _string(value, "material", ""),
            _number(value, "confidence", 0.7),
            _string(value, "source_sha256", ""),
        )


# {
#   責務: [load_guidance: local hint JSON fileをschema validationして読む]
#   処理: [read UTF-8 JSON, reject malformed files, and never access a network]
#   引数: [path: local JSON path]
#   戻り値: [GuidanceHints: validated local annotations]
# }
def load_guidance(path: Path) -> GuidanceHints:
    try:
        if Path(path).stat().st_size > 1024 * 1024:
            raise ValueError("guidance file exceeds the 1-megabyte limit")
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("guidance file is not readable UTF-8 JSON") from error
    return GuidanceHints.from_dict(value)


# {
#   責務: [save_guidance: local guidance annotationsをatomic JSON fileへ保存する]
#   処理: [write normalized contract via temporary file and replace destination]
#   引数: [path: local output file, hints: validated user annotations]
#   戻り値: [Path: saved local path]
# }
def save_guidance(path: Path, hints: GuidanceHints) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(hints.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(destination)
    return destination


# {
#   責務: [apply_guidance_prior: sparse annotationsでenhancement region blendと矛盾警告を作る]
#   処理: [use confidence as a soft alpha, preserve observed/excluded pixels, and do not treat hint as ground truth]
#   引数: [observed: prepared RGB image, enhanced: candidate RGB image, hints: user annotations]
#   戻り値: [tuple[Image.Image, tuple[str, ...]]: guided candidate and contradiction warnings]
# }
def apply_guidance_prior(
    observed: Image.Image, enhanced: Image.Image, hints: GuidanceHints
) -> tuple[Image.Image, tuple[str, ...]]:
    source = observed.convert("RGB")
    candidate = enhanced.convert("RGB")
    if source.size != candidate.size:
        raise ValueError("guidance images must share the same dimensions")
    if not hints.points and not hints.scribbles:
        return candidate, detect_guidance_conflicts(source, hints)
    reinforce = Image.new("L", source.size, 0)
    preserve = Image.new("L", source.size, 0)
    _draw_hints(reinforce, preserve, hints)
    reinforce_alpha = reinforce.point(lambda value: round(value * hints.confidence))
    preserve_alpha = preserve.point(lambda value: round(value * hints.confidence))
    guided = Image.composite(candidate, source, reinforce_alpha)
    guided = Image.composite(source, guided, preserve_alpha)
    return guided, detect_guidance_conflicts(source, hints)


# {
#   責務: [detect_guidance_conflicts: user hintsとsource pixelsの明示的な不一致を列挙する]
#   処理: [check sampled colors and conflicting surface/hidden annotations with confidence threshold]
#   引数: [source: source image, hints: sparse annotations]
#   戻り値: [tuple[str, ...]: warning codes, empty when no detectable conflict]
# }
def detect_guidance_conflicts(source: Image.Image, hints: GuidanceHints) -> tuple[str, ...]:
    image = source.convert("RGB")
    warnings = []
    for index, point in enumerate(hints.points):
        if point.label == "color_sample" and point.expected_rgb and point.confidence >= 0.6:
            actual = image.getpixel(
                (
                    min(image.width - 1, round(point.x * (image.width - 1))),
                    min(image.height - 1, round(point.y * (image.height - 1))),
                )
            )
            distance = math.sqrt(
                sum(
                    (first - second) ** 2
                    for first, second in zip(actual, point.expected_rgb, strict=True)
                )
            )
            if distance > 96:
                warnings.append(f"color_sample_conflict:{index}")
    confident_points = [point for point in hints.points if point.confidence >= 0.65]
    for first_index, first in enumerate(confident_points):
        for second_index, second in enumerate(confident_points[first_index + 1 :], first_index + 1):
            conflicting_labels = {first.label, second.label} in (
                {"surface", "hidden_object"},
                {"background", "hidden_object"},
            )
            if conflicting_labels and math.hypot(first.x - second.x, first.y - second.y) < 0.04:
                warnings.append(f"overlapping_point_hints:{first_index}:{second_index}")
    semantic_conflict = (
        hints.category in {"paper", "film"}
        and hints.material in {"cloth", "thin_cloth", "thick_cloth"}
    ) or (hints.category in {"cloth", "clothing", "shirt"} and hints.material == "paper")
    if semantic_conflict:
        warnings.append("semantic_category_material_conflict")
    labels = {stroke.label for stroke in hints.scribbles if stroke.confidence >= 0.65}
    if "surface" in labels and "hidden_object" in labels:
        surface = _stroke_mask(image.size, hints, "surface")
        hidden = _stroke_mask(image.size, hints, "hidden_object")
        overlap = ImageChops.multiply(surface, hidden)
        if ImageStat.Stat(overlap).mean[0] > 0:
            warnings.append("overlapping_surface_hidden_scribbles")
    return tuple(warnings)


# {
#   責務: [_draw_hints: points/strokesをsoft region masksへrasterizeする]
#   処理: [hidden/edge hints prefer enhancement; surface/background/exclude preserve observation]
#   引数: [reinforce: candidate region, preserve: observation region, hints: normalized annotations]
#   戻り値: []
# }
def _draw_hints(reinforce: Image.Image, preserve: Image.Image, hints: GuidanceHints) -> None:
    for point in hints.points:
        mask = reinforce if point.label in {"hidden_object", "edge"} else preserve
        x, y = _pixel(point.x, point.y, mask.size)
        radius = max(2, round(min(mask.size) * 0.025))
        ImageDraw.Draw(mask).ellipse(
            (x - radius, y - radius, x + radius, y + radius), fill=round(255 * point.confidence)
        )
    for stroke in hints.scribbles:
        mask = reinforce if stroke.label in {"hidden_object", "contour"} else preserve
        coordinates = [_pixel(x, y, mask.size) for x, y in stroke.points]
        width = max(1, round(min(mask.size) * stroke.width))
        drawer = ImageDraw.Draw(mask)
        if len(coordinates) == 1:
            x, y = coordinates[0]
            drawer.ellipse(
                (x - width // 2, y - width // 2, x + width // 2, y + width // 2),
                fill=round(255 * stroke.confidence),
            )
        else:
            drawer.line(
                coordinates, fill=round(255 * stroke.confidence), width=width, joint="curve"
            )
            radius = width // 2
            for x, y in (coordinates[0], coordinates[-1]):
                drawer.ellipse(
                    (x - radius, y - radius, x + radius, y + radius),
                    fill=round(255 * stroke.confidence),
                )


# {
#   責務: [_stroke_mask: selected scribble labelだけのmaskを生成する]
#   処理: [rasterize matching strokes with their confidence and normalized width]
#   引数: [size: source image dimensions, hints: guidance document, label: requested region]
#   戻り値: [Image.Image: 8-bit region mask]
# }
def _stroke_mask(size: tuple[int, int], hints: GuidanceHints, label: str) -> Image.Image:
    selected = GuidanceHints(
        scribbles=tuple(stroke for stroke in hints.scribbles if stroke.label == label)
    )
    preserve = Image.new("L", size, 0)
    reinforce = Image.new("L", size, 0)
    preserve = Image.new("L", size, 0)
    _draw_hints(reinforce, preserve, selected)
    return preserve if label in {"surface", "exclude"} else reinforce


# {
#   責務: [_pixel: normalized coordinateをimage pixel coordinateへ変換する]
#   処理: [clamp rounding at the last valid pixel]
#   引数: [x/y: normalized coordinate, size: image dimensions]
#   戻り値: [tuple[int, int]: pixel coordinate]
# }
def _pixel(x: float, y: float, size: tuple[int, int]) -> tuple[int, int]:
    return round(x * (size[0] - 1)), round(y * (size[1] - 1))


# {
#   責務: [_validate_unit: finite normalized scalarを検証する]
#   処理: [reject booleans, infinities, NaN, and out-of-range values]
#   引数: [value: number, label: field identifier]
#   戻り値: []
# }
def _validate_unit(value: float, label: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"{label} must be finite and between zero and one")


# {
#   責務: [_number: typed scalar fieldをfinite floatへ読み込む]
#   処理: [reject strings and booleans instead of coercing untrusted JSON]
#   引数: [row: mapping, key: field name, default: optional numeric fallback]
#   戻り値: [float: validated numeric value]
# }
def _number(row: dict[str, Any], key: str, default: float | None = None) -> float:
    value = row.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


# {
#   責務: [_number_pair: two coordinate valuesをvalidateする]
#   処理: [reject malformed coordinate pairs]
#   引数: [value: untrusted JSON sequence]
#   戻り値: [tuple[float, float]: validated normalized coordinates]
# }
def _number_pair(value: object) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("scribble coordinates require pairs")
    return float(_number({"value": value[0]}, "value")), float(
        _number({"value": value[1]}, "value")
    )


# {
#   責務: [_string: typed text fieldを読み込む]
#   処理: [reject arbitrary object coercion]
#   引数: [row: mapping, key: field name, default: text fallback]
#   戻り値: [str: validated text]
# }
def _string(row: dict[str, Any], key: str, default: str = "") -> str:
    value = row.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


# {
#   責務: [score_guidance_alignment: same hint dimensionsでcandidate compatibilityを比較する]
#   処理: [measure detail support in hidden/contour regions, source preservation elsewhere, and expected color samples]
#   引数: [observed: prepared baseline, candidate: candidate pixels, hints: normalized guidance]
#   戻り値: [tuple[float, dict[str, float]]: weighted compatibility score and named metrics]
# }
def score_guidance_alignment(
    observed: Image.Image, candidate: Image.Image, hints: GuidanceHints
) -> tuple[float, dict[str, float]]:
    source = observed.convert("RGB")
    output = candidate.convert("RGB")
    if source.size != output.size:
        raise ValueError("guidance scoring images must share the same dimensions")
    reinforce = Image.new("L", source.size, 0)
    preserve = Image.new("L", source.size, 0)
    _draw_hints(reinforce, preserve, hints)
    metrics: dict[str, float] = {}
    weights: dict[str, float] = {}
    if ImageStat.Stat(reinforce).mean[0] > 0:
        source_edges = source.convert("L").filter(ImageFilter.FIND_EDGES)
        output_edges = output.convert("L").filter(ImageFilter.FIND_EDGES)
        source_energy = ImageStat.Stat(source_edges, reinforce).mean[0] / 255
        output_energy = ImageStat.Stat(output_edges, reinforce).mean[0] / 255
        metrics["detail_support"] = min(1.0, output_energy / max(source_energy, 0.02))
        weights["detail_support"] = ImageStat.Stat(reinforce).mean[0] / 255
    if ImageStat.Stat(preserve).mean[0] > 0:
        difference = ImageChops.difference(source, output).convert("L")
        similarity = 1.0 - ImageStat.Stat(difference, preserve).mean[0] / 255
        metrics["observation_preservation"] = max(0.0, similarity)
        weights["observation_preservation"] = ImageStat.Stat(preserve).mean[0] / 255
    color_scores = []
    color_weights = []
    for point in hints.points:
        if point.label != "color_sample" or point.expected_rgb is None:
            continue
        location = _pixel(point.x, point.y, source.size)
        actual = output.getpixel(location)
        distance = math.sqrt(
            sum(
                (first - second) ** 2
                for first, second in zip(actual, point.expected_rgb, strict=True)
            )
        )
        color_scores.append(max(0.0, 1.0 - distance / (math.sqrt(3) * 255)))
        color_weights.append(point.confidence)
    if color_scores:
        metrics["expected_color"] = sum(
            score * weight for score, weight in zip(color_scores, color_weights, strict=True)
        ) / sum(color_weights)
        weights["expected_color"] = sum(color_weights) / len(color_weights)
    if not metrics:
        return 0.5, {"semantic_only": 0.5}
    total_weight = sum(weights.values())
    return sum(metrics[name] * weights[name] for name in metrics) / total_weight, metrics
