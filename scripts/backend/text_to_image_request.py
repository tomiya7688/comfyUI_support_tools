"""Backend-neutral inputs for one txt2img generation request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TextToImageRequest:
    prompt: str
    negative: str
    checkpoint: str
    steps: int
    cfg: float
    sampler: str
    width: int
    height: int
    use_model_vae: bool = True
    save_images: bool = True
    enable_hr: bool = False
    hr_scale: float = 1.5
    hr_upscaler: str = ""
    hr_second_pass_steps: int = 20
    denoising_strength: float = 0.7
    workflow_path: Path | None = None
    model_overrides: dict[str, str] | None = None
