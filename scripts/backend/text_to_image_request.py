"""Backend-neutral inputs for one txt2img generation request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [TextToImageRequest: one backend-neutral txt2img operationのsettingsを保持する]
#   処理: [generation, optional hires, workflow, model override and VAE valuesをtransportする]
#   フィールド: [prompt, negative, checkpoint, steps, cfg, sampler, dimensions, hires, workflow, overrides, VAE]
# }
# {
#   責務: [TextToImageRequest: one backend-neutral txt2img operationのsettingsを保持する]
#   処理: [generation, optional hires, workflow, model override and VAE valuesをtransportする]
#   フィールド: [prompt, negative, checkpoint, steps, cfg, sampler, width, height, hires options, workflow_path, model_overrides, vae_name]
# }
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
    vae_name: str = ""
