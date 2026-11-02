"""Extensible still-first anime loop animation and GIF encoding primitives."""

from .application import AnimationBackendRegistry, Txt2GifApplication
from .contracts import (
    AnimationFrameBackend,
    AnimationLayer,
    DitherMode,
    MotionKind,
    Txt2GifRequest,
    Txt2GifResult,
)
from .pipeline import create_txt2gif, encode_gif, render_key_art_loop, seal_loop

__all__ = [
    "AnimationFrameBackend",
    "AnimationBackendRegistry",
    "AnimationLayer",
    "DitherMode",
    "MotionKind",
    "Txt2GifRequest",
    "Txt2GifResult",
    "Txt2GifApplication",
    "create_txt2gif",
    "encode_gif",
    "render_key_art_loop",
    "seal_loop",
]
