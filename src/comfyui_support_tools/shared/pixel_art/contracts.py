"""Shared settings and value objects for the Pixel Art Creator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from PIL import Image


# {
# 責務: [PixelArtCategory: common asset categories supported by every entry workflow]
# フィールド: [category values: character, monster, portrait, item, tile, effect, background, UI]
# 処理: [settings validation and category-aware extensions]
# }
class PixelArtCategory(str, Enum):
    CHARACTER = "character"
    MONSTER = "monster"
    PORTRAIT = "portrait"
    FACE_ICON = "face_icon"
    ITEM = "item"
    EQUIPMENT = "equipment"
    EFFECT = "effect"
    UI_ICON = "ui_icon"
    BACKGROUND = "background"
    TILE = "tile"
    SPRITE_SHEET = "sprite_sheet"


# {
# 責務: [PixelArtSettings: text/image/retouchで共有する生成と編集制約]
# フィールド: [size, category, palette, crop, dither, transparency, preview scale]
# 処理: [single source of truth for strict grid and palette output]
# }
@dataclass(frozen=True)
class PixelArtSettings:
    size: int = 64
    custom_size: tuple[int, int] | None = None
    category: PixelArtCategory = PixelArtCategory.CHARACTER
    palette_mode: str = "auto"
    color_count: int = 16
    palette: tuple[tuple[int, int, int, int], ...] = ()
    transparent: bool = True
    crop_policy: str = "fit"
    dithering: str = "none"
    preview_scale: int = 8


# {
# 責務: [PixelArtRequest: prompt駆動生成と候補数を指定する]
# フィールド: [prompt, negative prompt, settings, style, seed, candidates]
# 処理: [shared text workflow input for replaceable generation backends]
# }
@dataclass(frozen=True)
class PixelArtRequest:
    prompt: str
    settings: PixelArtSettings = PixelArtSettings()
    negative_prompt: str = ""
    style: str = "modern_indie"
    seed: int | None = None
    candidate_count: int = 1


# {
# 責務: [PixelGrid: fixed-size RGBA pixels in row-major integer coordinates]
# フィールド: [width, height, pixels]
# 処理: [preserve strict pixel-level state independent of image backend]
# }
@dataclass(frozen=True)
class PixelGrid:
    width: int
    height: int
    pixels: tuple[tuple[int, int, int, int], ...]


# {
# 責務: [PixelMetric: deterministic evaluator scores and issue counts]
# フィールド: [score map, palette size, islands, alias, alpha, native readability]
# 処理: [provide comparable pixel-specific feedback without claiming semantic judgment]
# }
@dataclass(frozen=True)
class PixelMetric:
    score: float
    values: tuple[tuple[str, float], ...]
    counts: tuple[tuple[str, int], ...]
    notes: tuple[str, ...]


# {
# 責務: [PixelEdit: one reversible pixel-grid edit operation]
# フィールド: [kind, coordinates, color, bounds]
# 処理: [pencil/eraser/fill/replace/mirror/line operations]
# }
@dataclass(frozen=True)
class PixelEdit:
    kind: str
    x: int = 0
    y: int = 0
    color: tuple[int, int, int, int] = (0, 0, 0, 0)
    source_color: tuple[int, int, int, int] | None = None
    end_x: int | None = None
    end_y: int | None = None


# {
# 責務: [PixelArtResult: processed grid, metrics and exportable files]
# フィールド: [grid, metric, preview, metadata]
# 処理: [unify result contract across text/image/retouch workflows]
# }
@dataclass(frozen=True)
class PixelArtResult:
    grid: PixelGrid
    metric: PixelMetric
    preview: Image.Image
    metadata: dict[str, object]


# {
# 責務: [PixelTextBackend: AI/workflow adapter contract for prompt-based candidates]
# フィールド: [generate callable]
# 処理: [decouple ComfyUI/model routing from deterministic pixel processing]
# }
class PixelTextBackend(Protocol):
    # {
    # 責務: [generate: create one or more draft images for a pixel request]
    # 処理: [let the backend decide native-grid or semantic-draft strategy]
    # 引数: [request: pixel prompt and shared settings]
    # 戻り値: [images: draft images for deterministic pixel rendering]
    # }
    def generate(self, request: PixelArtRequest) -> tuple[object, ...]: ...
