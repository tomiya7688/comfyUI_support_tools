"""Backend-neutral inputs for one txt2img generation request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.comfyui_support_tools.shared.contracts.resolved_prompt import ResolvedPrompt


# {
#   責務: [TextToImageRequest: backend非依存の1回分画像生成requestを表す]
#   フィールド: [prompt: 互換用正prompt, negative: 互換用負prompt, resolved_prompt: Wildcard Applicationの確定結果, checkpoint: model名, steps: 生成step数, cfg: CFG値, sampler: sampler名, width: 画像幅, height: 画像高さ]
#   処理: [resolved_promptを保持し, 既存adapter向け文字列fieldとの段階移行を可能にする]
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
    resolved_prompt: ResolvedPrompt | None = None
