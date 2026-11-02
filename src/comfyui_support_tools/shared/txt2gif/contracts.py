"""Typed contracts for short seamless anime loop generation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


# {
#   責務: [MotionKind: repeatable small animation categoriesを列挙する]
#   フィールド: [BLINK, BREATHING, HAIR_SWAY, CLOTH_SWAY, PARTICLES, GLOW, FLAME, CUSTOM]
# }
class MotionKind(str, Enum):
    BLINK = "blink"
    BREATHING = "breathing"
    HAIR_SWAY = "hair_sway"
    CLOTH_SWAY = "cloth_sway"
    PARTICLES = "particles"
    GLOW = "glow"
    FLAME = "flame"
    CUSTOM = "custom"


# {
#   責務: [DitherMode: GIF global palette quantizationのdither policyを指定する]
#   フィールド: [NONE, FLOYD_STEINBERG]
# }
class DitherMode(str, Enum):
    NONE = "none"
    FLOYD_STEINBERG = "floyd_steinberg"


# {
#   責務: [AnimationLayer: clean plate上へmotionさせるRGBA subject layerを表す]
#   フィールド: [name, rgba_png, x/y amplitude, phase, motion kind]
# }
@dataclass(frozen=True, slots=True)
class AnimationLayer:
    name: str
    rgba_png: bytes
    amplitude_x: float
    amplitude_y: float
    phase: float = 0.0
    kind: MotionKind = MotionKind.CUSTOM

    # {
    #   責務: [__post_init__: animated layer inputとmotion parameterをvalidateする]
    #   処理: [reject empty layers, non-finite values, and excessive displacement]
    #   引数: [self: cutout RGBA layer and periodic motion]
    #   戻り値: []
    #   エラー: [ValueError: malformed layer]
    # }
    def __post_init__(self) -> None:
        if not self.name.strip() or not isinstance(self.rgba_png, bytes) or not self.rgba_png:
            raise ValueError("animation layers require a name and RGBA image data")
        if not isinstance(self.kind, MotionKind):
            raise TypeError("layer motion kind must use the declared MotionKind enum")
        values = (self.amplitude_x, self.amplitude_y, self.phase)
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in values):
            raise TypeError("layer motion values must be numbers")
        if any(not math.isfinite(value) for value in values):
            raise ValueError("layer motion values must be finite")
        if abs(self.amplitude_x) > 256 or abs(self.amplitude_y) > 256:
            raise ValueError("layer displacement cannot exceed 256 pixels")


# {
#   責務: [Txt2GifRequest: still generation, loop motion and GIF constraintsをまとめる]
#   フィールド: [prompt, dimensions, fps/frame count, duration, dither, color and size targets, layers]
# }
@dataclass(frozen=True, slots=True)
class Txt2GifRequest:
    prompt: str
    output_path: Path
    width: int = 512
    height: int = 512
    fps: int = 8
    frame_count: int = 16
    color_count: int = 128
    dither: DitherMode = DitherMode.FLOYD_STEINBERG
    maximum_file_bytes: int = 8_000_000
    minimum_dimension: int = 128
    background_rgb: tuple[int, int, int] = (255, 255, 255)
    motion_layers: tuple[AnimationLayer, ...] = ()

    # {
    #   責務: [__post_init__: animation request duration, palette and output constraintsをvalidateする]
    #   処理: [bound dimensions, short-loop frame cadence, palette size and file budget]
    #   引数: [self: immutable Txt2GIF request]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: invalid generation request]
    # }
    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("animation prompt must not be empty")
        if not isinstance(self.output_path, Path):
            raise TypeError("output_path must be a pathlib Path")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (self.width, self.height)
        ):
            raise TypeError("canvas dimensions must be integers")
        if min(self.width, self.height) < 64 or max(self.width, self.height) > 4096:
            raise ValueError("canvas dimensions must be between 64 and 4096 pixels")
        if isinstance(self.fps, bool) or not isinstance(self.fps, int) or not 4 <= self.fps <= 15:
            raise ValueError("GIF frame rate must be between 4 and 15 fps")
        if (
            isinstance(self.frame_count, bool)
            or not isinstance(self.frame_count, int)
            or not 8 <= self.frame_count <= 48
        ):
            raise ValueError("short anime loops must contain 8 to 48 frames")
        if self.width * self.height * self.frame_count > 32_000_000:
            raise ValueError("animation request exceeds the 32-megapixel total frame budget")
        if (
            isinstance(self.color_count, bool)
            or not isinstance(self.color_count, int)
            or not 2 <= self.color_count <= 256
        ):
            raise ValueError("GIF color count must be between 2 and 256")
        if not isinstance(self.dither, DitherMode):
            raise TypeError("dither must use a declared DitherMode")
        if (
            isinstance(self.maximum_file_bytes, bool)
            or not isinstance(self.maximum_file_bytes, int)
            or self.maximum_file_bytes <= 0
            or isinstance(self.minimum_dimension, bool)
            or not isinstance(self.minimum_dimension, int)
            or self.minimum_dimension < 64
        ):
            raise ValueError("file budget must be positive and minimum dimension at least 64")
        if self.minimum_dimension > min(self.width, self.height):
            raise ValueError("minimum dimension cannot exceed the requested canvas")
        if len(self.background_rgb) != 3 or any(
            isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255
            for value in self.background_rgb
        ):
            raise ValueError("background_rgb must contain three byte values")
        if any(not isinstance(layer, AnimationLayer) for layer in self.motion_layers):
            raise TypeError("motion_layers must contain AnimationLayer values")


# {
#   責務: [AnimationFrameBackend: reference-aware still/animation backend interfaceを定義する]
#   フィールド: [generate_still, extract_layers]
#   処理: [backends can use txt2img, AnimateDiff, segmentation, or keyframe interpolation]
# }
class AnimationFrameBackend(Protocol):
    # {
    #   責務: [generate_still: promptからcanonical reference frame PNGを生成する]
    #   処理: [generate one fixed composition used as identity/style anchor]
    #   引数: [request: animation request]
    #   戻り値: [bytes: PNG still image]
    # }
    def generate_still(self, request: Txt2GifRequest) -> bytes: ...

    # {
    #   責務: [extract_layers: canonical stillからclean plateと動かすcutoutを作成する]
    #   処理: [segment selected subject regions without regenerating the full background]
    #   引数: [still_png: canonical reference frame, request: motion layer intent]
    #   戻り値: [tuple[bytes, tuple[AnimationLayer, ...]]: clean plate and periodic layers]
    # }
    def extract_layers(
        self, still_png: bytes, request: Txt2GifRequest
    ) -> tuple[bytes, tuple[AnimationLayer, ...]]: ...


# {
#   責務: [Txt2GifResult: rendered GIF outputとloop/palette diagnosticsを返す]
#   フィールド: [path, frame count, fps, colors, bytes, seam error, actual dimensions]
# }
@dataclass(frozen=True, slots=True)
class Txt2GifResult:
    path: Path
    frame_count: int
    fps: int
    color_count: int
    file_bytes: int
    seam_error: float
    width: int
    height: int
