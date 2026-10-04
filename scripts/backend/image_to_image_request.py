"""Backend-neutral inputs for one img2img generation request."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# {
# 責務: [ImageToImageRequest: 画像入力を使う生成要求の設定を不変データとして運ぶ]
# フィールド: [image_path: 入力画像, prompt: 正プロンプト, negative: 負プロンプト, checkpoint: 使用モデル,
# steps: sampling step数, cfg: guidance値, sampler: sampler名, denoise: 変換強度,
# width: 出力幅, height: 出力高, vae_name: 任意のVAE名]
# 処理: [1: image-to-image backendへ必要な設定を集約する]
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
