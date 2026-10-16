"""Named inputs shared by backend-specific generation profile factories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [GenerationProfileInputs: backend別profile factoryへ渡す共通設定値を保持する]
#   フィールド: [a1111_api_url: A1111 API URL, comfyui_api_url: ComfyUI API URL, a1111_directory: A1111 runtime path, runtime_directory: 選択中runtime path, date_folder: 日付別保存folder名, pixai_tagger_url: PixAI Tagger URL]
# }
@dataclass(frozen=True)
class GenerationProfileInputs:
    a1111_api_url: str
    comfyui_api_url: str
    a1111_directory: Path
    runtime_directory: Path
    date_folder: str
    pixai_tagger_url: str
