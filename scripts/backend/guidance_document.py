"""Application-side value objects for the file-based Touka guidance contract."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# {
#   責務: [GuidancePoint: source-relative point hintを保持する]
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
    #   責務: [__post_init__: point coordinate, label and sample colorを検証する]
    #   処理: [validate the stable JSON interchange contract]
    #   引数: [self: one normalized point hint]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        _unit(self.x, "x")
        _unit(self.y, "y")
        _unit(self.confidence, "confidence")
        if self.label not in {"surface", "hidden_object", "background", "edge", "color_sample"}:
            raise ValueError("unsupported point hint label")
        if self.label == "color_sample" and self.expected_rgb is None:
            raise ValueError("color_sample requires an expected RGB triplet")
        if self.expected_rgb is not None and (
            not isinstance(self.expected_rgb, tuple)
            or len(self.expected_rgb) != 3
            or any(
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255
                for value in self.expected_rgb
            )
        ):
            raise ValueError("expected_rgb must contain three byte values")


# {
#   責務: [GuidanceScribble: normalized brush path and soft labelを保持する]
#   フィールド: [points, label, width, confidence]
# }
@dataclass(frozen=True, slots=True)
class GuidanceScribble:
    points: tuple[tuple[float, float], ...]
    label: str
    width: float = 0.025
    confidence: float = 0.7

    # {
    #   責務: [__post_init__: brush path, width and labelをvalidateする]
    #   処理: [bound annotation size and normalized geometry]
    #   引数: [self: one scribble hint]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.points, tuple) or not 1 <= len(self.points) <= 10000:
            raise ValueError("scribble must contain 1 to 10000 points")
        if self.label not in {"surface", "hidden_object", "exclude", "contour"}:
            raise ValueError("unsupported scribble label")
        _unit(self.width, "width")
        _unit(self.confidence, "confidence")
        if self.width == 0:
            raise ValueError("scribble width must be positive")
        for x, y in self.points:
            _unit(x, "x")
            _unit(y, "y")


# {
#   責務: [GuidanceHints: GUIとTouka CLI間のguidance-hints.v1 file contractを表す]
#   フィールド: [points, scribbles, category, material, confidence, source_sha256]
# }
@dataclass(frozen=True, slots=True)
class GuidanceHints:
    points: tuple[GuidancePoint, ...] = ()
    scribbles: tuple[GuidanceScribble, ...] = ()
    category: str = ""
    material: str = ""
    confidence: float = 0.7
    source_sha256: str = ""

    # {
    #   責務: [__post_init__: semantic labels, item counts and source image bindingをvalidateする]
    #   処理: [maintain the versioned file interchange constraints]
    #   引数: [self: optional guidance annotations]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not isinstance(self.points, tuple) or not isinstance(self.scribbles, tuple):
            raise TypeError("guidance annotations must be immutable tuples")
        if len(self.points) > 128 or len(self.scribbles) > 128:
            raise ValueError("guidance hint limits exceeded")
        if self.category not in {
            "",
            "generic",
            "clothing",
            "cloth",
            "shirt",
            "skin",
            "paper",
            "film",
            "other",
        }:
            raise ValueError("unsupported guidance category")
        if self.material not in {
            "",
            "cloth",
            "thin_cloth",
            "thick_cloth",
            "paper",
            "plastic",
            "glass",
            "other",
        }:
            raise ValueError("unsupported guidance material")
        _unit(self.confidence, "confidence")
        if self.source_sha256 and not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        if any(not isinstance(point, GuidancePoint) for point in self.points):
            raise TypeError("points must contain GuidancePoint values")
        if any(not isinstance(stroke, GuidanceScribble) for stroke in self.scribbles):
            raise TypeError("scribbles must contain GuidanceScribble values")

    # {
    #   責務: [to_dict: guidance objectをJSON-compatible objectへserializeする]
    #   処理: [preserve normalized annotations and source hash]
    #   引数: [self: file contract]
    #   戻り値: [dict[str, object]: guidance-hints.v1 payload]
    # }
    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "guidance-hints.v1",
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
#   責務: [load_guidance: UI側guidance documentを安全なschemaで読む]
#   処理: [bound JSON size and validate external contract fields]
#   引数: [path: local guidance JSON]
#   戻り値: [GuidanceHints: immutable annotations]
# }
def load_guidance(path: Path) -> GuidanceHints:
    source = Path(path)
    try:
        if source.stat().st_size > 1024 * 1024:
            raise ValueError("guidance document exceeds one megabyte")
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("guidance document is not readable UTF-8 JSON") from error
    if not isinstance(value, dict) or value.get("schema") != "guidance-hints.v1":
        raise ValueError("guidance schema must be guidance-hints.v1")
    point_rows = value.get("points", [])
    stroke_rows = value.get("scribbles", [])
    if not isinstance(point_rows, list) or not isinstance(stroke_rows, list):
        raise ValueError("guidance points and scribbles must be arrays")
    if len(point_rows) > 128 or len(stroke_rows) > 128:
        raise ValueError("guidance hint limits exceeded")
    points = tuple(
        GuidancePoint(
            _number(row, "x"),
            _number(row, "y"),
            _string(row, "label"),
            _number(row, "confidence", 0.7),
            tuple(row["expected_rgb"]) if row.get("expected_rgb") is not None else None,
        )
        for row in point_rows
        if isinstance(row, dict)
    )
    strokes = tuple(
        GuidanceScribble(
            tuple(_pair(pair) for pair in row.get("points", [])),
            _string(row, "label"),
            _number(row, "width", 0.025),
            _number(row, "confidence", 0.7),
        )
        for row in stroke_rows
        if isinstance(row, dict)
    )
    if len(points) != len(point_rows) or len(strokes) != len(stroke_rows):
        raise ValueError("each point and scribble must be an object")
    return GuidanceHints(
        points,
        strokes,
        _string(value, "category", ""),
        _string(value, "material", ""),
        _number(value, "confidence", 0.7),
        _string(value, "source_sha256", ""),
    )


# {
#   責務: [save_guidance: local hint documentをatomic JSONで保存する]
#   処理: [write adjacent temporary file and replace destination]
#   引数: [path: local output path, hints: validated guidance object]
#   戻り値: [Path: saved path]
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
#   責務: [_unit: normalized finite scalarをvalidateする]
#   処理: [reject bool, NaN, infinity and out-of-range values]
#   引数: [value: number, name: field]
#   戻り値: []
# }
def _unit(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"{name} must be finite and between zero and one")


# {
#   責務: [_number: JSON numberを型強制無しで取得する]
#   処理: [reject strings and bool values]
#   引数: [row: JSON object, name: field, default: fallback]
#   戻り値: [float: numeric value]
# }
def _number(row: dict[str, Any], name: str, default: float | None = None) -> float:
    value = row.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


# {
#   責務: [_string: JSON string fieldを取得する]
#   処理: [reject implicit text coercion]
#   引数: [row: JSON object, name: field, default: fallback]
#   戻り値: [str: field value]
# }
def _string(row: dict[str, Any], name: str, default: str = "") -> str:
    value = row.get(name, default)
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


# {
#   責務: [_pair: normalized coordinate pairをvalidateする]
#   処理: [reject malformed input before constructing stroke]
#   引数: [value: untrusted coordinate value]
#   戻り値: [tuple[float, float]: point]
# }
def _pair(value: object) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("scribble coordinate must be a pair")
    return float(_number({"value": value[0]}, "value")), float(
        _number({"value": value[1]}, "value")
    )
