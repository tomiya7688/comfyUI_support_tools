"""Backend-neutral inputs for one img2img generation request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [ImageToImageRequest: one backend-neutral img2img operationのinputsをimmutable value objectとして保持する]
#   処理: [carry source path, prompts, model, sampler, and dimensions]
#   フィールド: [image_path, prompt, negative, checkpoint, steps, cfg, sampler, denoise, width, height, vae_name]
# }
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
