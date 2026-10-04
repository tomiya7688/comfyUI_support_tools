"""Backend-neutral inputs for one txt2img generation request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# {
# 責務: [TextToImageRequest: テキスト生成設定を不変データとして運ぶ]
# フィールド: [prompt: 正プロンプト, negative: 負プロンプト, checkpoint: 使用モデル, steps: sampling step数,
# cfg: guidance値, sampler: sampler名, width: 出力幅, height: 出力高, enable_hr: 高解像度処理の有効状態,
# hr_scale: 拡大率, hr_upscaler: upscaler名, hr_second_pass_steps: 追加step数,
# denoising_strength: 高解像度処理の変換強度, workflow_path: ComfyUI workflow,
# model_overrides: node別model指定, vae_name: 任意のVAE名, use_model_vae: checkpoint内VAE使用指定,
# save_images: backend側の画像保存指定]
# 処理: [1: text-to-image backendへ生成条件を集約する]
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
