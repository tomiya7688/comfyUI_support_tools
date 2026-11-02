"""Normalized, appearance-free composition template contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from PIL import Image


Point = tuple[float, float]
BoundingBox = tuple[float, float, float, float]
Polygon = tuple[Point, ...]


# {
# 責務: [RegionRole: describe layout function without copying subject identity]
# フィールド: [roles for subject, environment, empty, and safe text regions]
# 処理: [keep template regions semantic only at composition-role level]
# }
class RegionRole(str, Enum):
    MAIN_SUBJECT = "main_subject"
    SUPPORTING_SUBJECT = "supporting_subject"
    FOREGROUND = "foreground_element"
    BACKGROUND = "background_element"
    MIDGROUND = "midground_element"
    TEXT_AREA = "text_area"
    EMPTY_SPACE = "empty_space"
    SALIENT = "salient_region"


# {
# 責務: [ExtractionLevel: select composition detail budget]
# フィールド: [LAYOUT, STRUCTURED, PRODUCTION]
# 処理: [increase abstract spatial evidence without adding appearance identity]
# }
class ExtractionLevel(str, Enum):
    LAYOUT = "layout"
    STRUCTURED = "structured"
    PRODUCTION = "production"


# {
# 責務: [AspectPolicy: declare non-distorting template adaptation]
# フィールド: [CROP, FIT, SMART_REFLOW]
# 処理: [fit different canvas aspect ratios without stretching source geometry]
# }
class AspectPolicy(str, Enum):
    CROP = "crop"
    FIT = "fit"
    SMART_REFLOW = "smart_reflow"


# {
# 責務: [CompositionRegion: store one appearance-free normalized layout region]
# フィールド: [id, role, bbox, polygon, relative_scale, depth_order, facing_direction, attention_weight, confidence]
# 処理: [validate coordinates and bounded measurements independent of source resolution]
# 引数: [region geometry and optional composition evidence]
# 戻り値: [None: immutable normalized region]
# }
@dataclass(frozen=True)
class CompositionRegion:
    id: str
    role: RegionRole
    bbox: BoundingBox
    polygon: Polygon = ()
    relative_scale: float = 1.0
    depth_order: int | None = None
    facing_direction: str | None = None
    attention_weight: float = 0.0
    confidence: float = 0.0

    # {
    # 責務: [CompositionRegion.__post_init__: enforce normalized region invariants]
    # 処理: [validate identifier, normalized box/polygon coordinates and finite evidence weights]
    # 引数: [self: composition region]
    # 戻り値: [None: valid immutable region or ValueError]
    # }
    def __post_init__(self) -> None:
        if not self.id.strip() or not math.isfinite(self.relative_scale) or self.relative_scale < 0:
            raise ValueError("region identifier and scale must be valid")
        if self.depth_order is not None and self.depth_order < 0:
            raise ValueError("region depth order must be nonnegative")
        _validate_box(self.bbox)
        for point in self.polygon:
            _validate_point(point)
        for value in (self.attention_weight, self.confidence):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("region evidence weights must be normalized to 0..1")


# {
# 責務: [_validate_point: validate a normalized 2D coordinate]
# 処理: [require finite x/y values inside the closed unit square]
# 引数: [point: normalized coordinate pair]
# 戻り値: [None: valid point or ValueError]
# }
def _validate_point(point: Point) -> None:
    if len(point) != 2 or any(not math.isfinite(value) or not 0 <= value <= 1 for value in point):
        raise ValueError("composition coordinates must be finite and normalized to 0..1")


# {
# 責務: [_validate_box: validate normalized x/y/width/height geometry]
# 処理: [require positive extents wholly inside the unit canvas]
# 引数: [bbox: normalized top-left box]
# 戻り値: [None: valid box or ValueError]
# }
def _validate_box(bbox: BoundingBox) -> None:
    if len(bbox) != 4 or any(not math.isfinite(value) for value in bbox):
        raise ValueError("composition box must have four finite values")
    x, y, width, height = bbox
    if width <= 0 or height <= 0 or x < 0 or y < 0 or x + width > 1 or y + height > 1:
        raise ValueError("composition box must be positive and contained within 0..1")


# {
# 責務: [HorizonLine: store an optional normalized horizon estimate]
# フィールド: [y, angle, confidence]
# 処理: [retain coarse horizon geometry without source pixels]
# }
@dataclass(frozen=True)
class HorizonLine:
    y: float
    angle: float = 0.0
    confidence: float = 0.0

    # {
    # 責務: [HorizonLine.__post_init__: validate horizon values]
    # 処理: [bound location and confidence, and constrain line angle]
    # 引数: [self: horizon estimate]
    # 戻り値: [None: valid estimate or ValueError]
    # }
    def __post_init__(self) -> None:
        if (
            not all(math.isfinite(value) for value in (self.y, self.angle, self.confidence))
            or not 0 <= self.y <= 1
            or not -90 <= self.angle <= 90
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("horizon position, angle, or confidence is outside its valid range")


# {
# 責務: [VanishingPoint: store an optional perspective convergence point]
# フィールド: [x, y, confidence]
# 処理: [retain a normalized perspective cue]
# }
@dataclass(frozen=True)
class VanishingPoint:
    x: float
    y: float
    confidence: float = 0.0

    # {
    # 責務: [VanishingPoint.__post_init__: validate normalized point values]
    # 処理: [bound point and confidence]
    # 引数: [self: vanishing point estimate]
    # 戻り値: [None: valid estimate or ValueError]
    # }
    def __post_init__(self) -> None:
        _validate_point((self.x, self.y))
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("vanishing-point confidence must be normalized to 0..1")


# {
# 責務: [PoseKeypoint: store one optional normalized skeleton point]
# フィールド: [name, point, visibility]
# 処理: [keep pose geometry separate from appearance labels]
# }
@dataclass(frozen=True)
class PoseKeypoint:
    name: str
    point: Point
    visibility: float

    # {
    # 責務: [PoseKeypoint.__post_init__: validate named body landmark evidence]
    # 処理: [require a name, normalized coordinates, and bounded visibility]
    # 引数: [self: pose landmark]
    # 戻り値: [None: valid keypoint or ValueError]
    # }
    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("pose keypoint name is required")
        _validate_point(self.point)
        if not math.isfinite(self.visibility) or not 0 <= self.visibility <= 1:
            raise ValueError("pose visibility must be normalized to 0..1")


# {
# 責務: [PoseSkeleton: store optional pose landmarks and their confidence]
# フィールド: [id, keypoints, confidence]
# 処理: [allow pose adapters to be omitted without blocking layout extraction]
# }
@dataclass(frozen=True)
class PoseSkeleton:
    id: str
    keypoints: tuple[PoseKeypoint, ...]
    confidence: float

    # {
    # 責務: [PoseSkeleton.__post_init__: validate pose result]
    # 処理: [require a stable ID and finite confidence]
    # 引数: [self: pose skeleton]
    # 戻り値: [None: valid pose or ValueError]
    # }
    def __post_init__(self) -> None:
        if (
            not self.id.strip()
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("pose skeleton identifier and confidence must be valid")


# {
# 責務: [DepthLayer: name normalized regions at one relative depth]
# フィールド: [order, region_ids, confidence]
# 処理: [represent front-to-back ordering only]
# }
@dataclass(frozen=True)
class DepthLayer:
    order: int
    region_ids: tuple[str, ...]
    confidence: float

    # {
    # 責務: [DepthLayer.__post_init__: validate one relative depth band]
    # 処理: [require nonnegative order, unique region references, and normalized confidence]
    # 引数: [self: relative depth layer]
    # 戻り値: [None: valid layer or ValueError]
    # }
    def __post_init__(self) -> None:
        if (
            self.order < 0
            or not self.region_ids
            or len(set(self.region_ids)) != len(self.region_ids)
        ):
            raise ValueError("depth layers need a nonnegative order and unique region IDs")
        if any(not region_id.strip() for region_id in self.region_ids):
            raise ValueError("depth region IDs cannot be empty")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("depth-layer confidence must be normalized to 0..1")


# {
# 責務: [DepthStructure: summarize optional relative depth layers]
# フィールド: [layers, confidence, measured]
# 処理: [distinguish provider measurements from missing depth evidence]
# }
@dataclass(frozen=True)
class DepthStructure:
    layers: tuple[DepthLayer, ...] = ()
    confidence: float = 0.0
    measured: bool = False

    # {
    # 責務: [DepthStructure.__post_init__: validate depth evidence]
    # 処理: [check normalized confidence and unique order values]
    # 引数: [self: depth result]
    # 戻り値: [None: valid structure or ValueError]
    # }
    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("depth confidence must be normalized to 0..1")
        if not isinstance(self.measured, bool):
            raise ValueError("depth measured flag must be boolean")
        if len({layer.order for layer in self.layers}) != len(self.layers):
            raise ValueError("depth layer orders must be unique")


# {
# 責務: [VisualWeightMap: store a coarse normalized attention grid]
# フィールド: [rows]
# 処理: [provide resolution-independent visual mass evidence]
# }
@dataclass(frozen=True)
class VisualWeightMap:
    rows: tuple[tuple[float, ...], ...]

    # {
    # 責務: [VisualWeightMap.__post_init__: validate bounded saliency cells]
    # 処理: [require a rectangular nonempty matrix and finite normalized values]
    # 引数: [self: visual weight grid]
    # 戻り値: [None: valid grid or ValueError]
    # }
    def __post_init__(self) -> None:
        if (
            not self.rows
            or not self.rows[0]
            or any(len(row) != len(self.rows[0]) for row in self.rows)
        ):
            raise ValueError("visual weight map must be a nonempty rectangular grid")
        if any(
            not math.isfinite(value) or not 0 <= value <= 1 for row in self.rows for value in row
        ):
            raise ValueError("visual weight cells must be normalized to 0..1")


# {
# 責務: [ExtractionProvenance: record abstract extraction lineage without storing source appearance]
# フィールド: [image_sha256, source_width, source_height, extraction_level, algorithms, warnings]
# 処理: [make generated evidence reproducible and report optional missing adapters]
# }
@dataclass(frozen=True)
class ExtractionProvenance:
    image_sha256: str
    source_width: int
    source_height: int
    extraction_level: ExtractionLevel
    algorithms: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    # {
    # 責務: [ExtractionProvenance.__post_init__: validate image lineage metadata]
    # 処理: [require a SHA-256 digest and positive source dimensions]
    # 引数: [self: image extraction provenance]
    # 戻り値: [None: valid provenance or ValueError]
    # }
    def __post_init__(self) -> None:
        if len(self.image_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.image_sha256
        ):
            raise ValueError("image provenance must contain a lowercase SHA-256 digest")
        if self.source_width <= 0 or self.source_height <= 0:
            raise ValueError("source dimensions must be positive")
        if not self.algorithms:
            raise ValueError("at least one extraction algorithm must be recorded")


# {
# 責務: [CompositionTemplate: define portable layout evidence for reuse]
# フィールド: [aspect_ratio, shot_type, camera_angle, horizon, vanishing_points, subject/environment/space regions, visual_weight_map, reading_flow, thirds_alignment, symmetry, diagonal_flow, pose_skeletons, facing_directions, depth_structure, text_safe_regions, optional_panel_layout, confidence, extraction_provenance]
# 処理: [store composition roles and normalized geometry while excluding character/style/color identity]
# 引数: [template fields: normalized coordinates and optional structural measurements]
# 戻り値: [None: valid immutable template or ValueError]
# }
@dataclass(frozen=True)
class CompositionTemplate:
    aspect_ratio: float
    shot_type: str
    camera_angle: str
    subject_regions: tuple[CompositionRegion, ...]
    confidence: float
    extraction_provenance: ExtractionProvenance
    horizon: HorizonLine | None = None
    vanishing_points: tuple[VanishingPoint, ...] = ()
    foreground_regions: tuple[CompositionRegion, ...] = ()
    midground_regions: tuple[CompositionRegion, ...] = ()
    background_regions: tuple[CompositionRegion, ...] = ()
    negative_space_regions: tuple[CompositionRegion, ...] = ()
    salient_regions: tuple[CompositionRegion, ...] = ()
    visual_weight_map: VisualWeightMap | None = None
    reading_flow: tuple[Point, ...] = ()
    thirds_alignment: tuple[str, ...] = ()
    symmetry: float | None = None
    diagonal_flow: float | None = None
    pose_skeletons: tuple[PoseSkeleton, ...] = ()
    facing_directions: tuple[tuple[str, str], ...] = ()
    depth_structure: DepthStructure = DepthStructure()
    text_safe_regions: tuple[CompositionRegion, ...] = ()
    optional_panel_layout: tuple[CompositionRegion, ...] = ()
    schema_version: int = 1

    # {
    # 責務: [CompositionTemplate.__post_init__: validate abstract template metadata]
    # 処理: [require positive aspect ratio, normalized scores, and valid optional flow measurements]
    # 引数: [self: composition template]
    # 戻り値: [None: valid template or ValueError]
    # }
    def __post_init__(self) -> None:
        if not math.isfinite(self.aspect_ratio) or not 0 < self.aspect_ratio <= 100:
            raise ValueError("template aspect ratio must be a finite positive value")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("template confidence must be normalized to 0..1")
        if self.symmetry is not None and (
            not math.isfinite(self.symmetry) or not 0 <= self.symmetry <= 1
        ):
            raise ValueError("template symmetry must be normalized to 0..1")
        if self.diagonal_flow is not None and (
            not math.isfinite(self.diagonal_flow) or not -180 <= self.diagonal_flow <= 180
        ):
            raise ValueError("diagonal flow angle must be within -180..180 degrees")
        if self.schema_version != 1 or not self.shot_type.strip() or not self.camera_angle.strip():
            raise ValueError("template schema version, shot type, and camera angle must be valid")
        if any(
            not region_id.strip() or not direction.strip()
            for region_id, direction in self.facing_directions
        ):
            raise ValueError("facing-direction records must contain nonempty IDs and directions")
        known_region_ids = {region.id for region in self.subject_regions}
        if any(
            region_id not in known_region_ids
            for layer in self.depth_structure.layers
            for region_id in layer.region_ids
        ):
            raise ValueError("depth layers may reference subject regions only")
        for point in self.reading_flow:
            _validate_point(point)
        if len({region.id for region in self.all_regions}) != len(self.all_regions):
            raise ValueError("composition region identifiers must be unique")

    # {
    # 責務: [all_regions: expose every layout region in stable category order]
    # 処理: [combine subject, depth, saliency, text-safe and panel regions]
    # 引数: [self: composition template]
    # 戻り値: [tuple[CompositionRegion, ...]: all region records]
    # }
    @property
    def all_regions(self) -> tuple[CompositionRegion, ...]:
        return (
            self.subject_regions
            + self.foreground_regions
            + self.midground_regions
            + self.background_regions
            + self.negative_space_regions
            + self.salient_regions
            + self.text_safe_regions
            + self.optional_panel_layout
        )


# {
# 責務: [SubjectAnalysisAdapter: define optional subject box/mask analysis]
# フィールド: [analyze callable]
# 処理: [supply model-based regions without coupling the core to a specific detector]
# 引数: [image: decoded source pixels]
# 戻り値: [tuple[CompositionRegion, ...]: normalized regions]
# }
class SubjectAnalysisAdapter(Protocol):
    # {
    # 責務: [analyze: detect composition-level subject regions]
    # 処理: [return normalized regions without identity/style metadata]
    # 引数: [image: RGB source image]
    # 戻り値: [tuple[CompositionRegion, ...]: detected subjects]
    # }
    def analyze(self, image: Image.Image) -> tuple[CompositionRegion, ...]: ...


# {
# 責務: [PoseAnalysisAdapter: define optional pose extraction]
# フィールド: [analyze callable]
# 処理: [attach pose skeletons only when an explicitly supplied adapter measures them]
# 引数: [image: decoded source pixels]
# 戻り値: [tuple[PoseSkeleton, ...]: normalized optional poses]
# }
class PoseAnalysisAdapter(Protocol):
    # {
    # 責務: [analyze: measure normalized pose keypoints]
    # 処理: [return skeletons with per-keypoint visibility evidence]
    # 引数: [image: RGB source image]
    # 戻り値: [tuple[PoseSkeleton, ...]: pose estimates]
    # }
    def analyze(self, image: Image.Image) -> tuple[PoseSkeleton, ...]: ...


# {
# 責務: [DepthAnalysisAdapter: define optional relative depth extraction]
# フィールド: [analyze callable]
# 処理: [return front-to-back region relations without requiring one depth model]
# 引数: [image: decoded source pixels, regions: current normalized regions]
# 戻り値: [DepthStructure: optional depth layers]
# }
class DepthAnalysisAdapter(Protocol):
    # {
    # 責務: [analyze: estimate relative depth organization]
    # 処理: [map known composition region IDs to measured depth layers]
    # 引数: [image: RGB source, regions: detected/fallback regions]
    # 戻り値: [DepthStructure: measured or partial depth result]
    # }
    def analyze(
        self, image: Image.Image, regions: tuple[CompositionRegion, ...]
    ) -> DepthStructure: ...


# {
# 責務: [PerspectiveAnalysisAdapter: define optional horizon and vanishing-point analysis]
# フィールド: [analyze callable]
# 処理: [return measurable perspective cues for architectural or landscape scenes]
# 引数: [image: decoded source pixels]
# 戻り値: [tuple[HorizonLine | None, tuple[VanishingPoint, ...]]: optional perspective evidence]
# }
class PerspectiveAnalysisAdapter(Protocol):
    # {
    # 責務: [analyze: estimate horizon and perspective convergence]
    # 処理: [return normalized cues with explicit confidence]
    # 引数: [image: RGB source image]
    # 戻り値: [tuple[HorizonLine | None, tuple[VanishingPoint, ...]]: perspective evidence]
    # }
    def analyze(
        self, image: Image.Image
    ) -> tuple[HorizonLine | None, tuple[VanishingPoint, ...]]: ...
