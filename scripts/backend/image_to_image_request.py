"""Backend-neutral inputs for one img2img generation request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageToImageRequest:
    image_path: Path
    prompt: str
    negative: str
    checkpoint: str
    steps: int
    cfg: float
    sampler: str
    denoise: float
    width: int
    height: int
    vae_name: str = ""
