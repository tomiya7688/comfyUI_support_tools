"""Resolve the selected generation backend's runtime defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from .generation_backend_types import GenerationBackendId


# {
#   責務: [BackendRuntimeProfile: 選択済みgeneration backendの実行時既定値を保持する]
#   フィールド: [backend: backend識別子, display_name: UI表示名, runtime_directory: runtime directory]
# }
@dataclass(frozen=True)
class BackendRuntimeProfile:
    backend: GenerationBackendId
    display_name: str
    runtime_directory: Path


# {
#   責務: [create_backend_runtime_profile: 選択されたbackendのruntime profileを作る]
#   処理: [1: backend識別子を正規化する, 2: 対応するruntimeと表示名を選ぶ, 3: fallback規則とoverrideを適用する]
#   引数: [backend: 起動時に選択されたbackend ID, a1111_directory: A1111 runtime path, comfyui_directory: ComfyUI runtime path, runtime_directory_override: 任意のruntime path override, fallback_backend: 未対応ID時のdefaultまたは厳密検証を示すNone]
#   戻り値: [BackendRuntimeProfile: backend ID・表示名・runtime pathを含むprofile]
#   エラー: [ValueError: 未対応IDかつfallback_backendがNoneの場合]
# }
def create_backend_runtime_profile(
    backend: str,
    a1111_directory: Path,
    comfyui_directory: Path,
    runtime_directory_override: str | Path | None = None,
    fallback_backend: GenerationBackendId | None = "a1111",
) -> BackendRuntimeProfile:
    normalized_backend = backend.strip().lower()
    backend_options = {
        "a1111": ("WebUI1111", Path(a1111_directory)),
        "comfyui": ("ComfyUI", Path(comfyui_directory)),
    }
    selected_backend = normalized_backend
    if selected_backend not in backend_options:
        if fallback_backend is None:
            raise ValueError(f"Unsupported runtime backend: {backend}")
        selected_backend = fallback_backend
    if selected_backend not in backend_options:
        raise ValueError(f"Unsupported fallback runtime backend: {selected_backend}")
    selected_backend_id = cast(GenerationBackendId, selected_backend)
    display_name, default_directory = backend_options[selected_backend_id]
    runtime_directory = (
        Path(runtime_directory_override).expanduser().resolve()
        if runtime_directory_override is not None
        else default_directory.resolve()
    )
    return BackendRuntimeProfile(selected_backend_id, display_name, runtime_directory)
