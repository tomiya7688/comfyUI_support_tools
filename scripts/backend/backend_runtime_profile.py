"""Resolve the selected generation backend's runtime defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [BackendRuntimeProfile: 選択済みgeneration backendの実行時既定値を保持する]
#   フィールド: [backend: backend識別子, display_name: UI表示名, runtime_directory: runtime directory]
# }
@dataclass(frozen=True)
class BackendRuntimeProfile:
    backend: str
    display_name: str
    runtime_directory: Path


# {
#   責務: [create_backend_runtime_profile: 選択されたbackendのruntime profileを作る]
#   処理: [1: backend識別子を正規化する, 2: 対応するruntimeと表示名を選ぶ, 3: overrideがあればruntime directoryへ適用する]
#   引数: [backend: 起動時に選択されたbackend ID, a1111_directory: A1111 runtime path, comfyui_directory: ComfyUI runtime path, runtime_directory_override: 任意のruntime path override]
#   戻り値: [BackendRuntimeProfile: backend ID・表示名・runtime pathを含むprofile]
# }
def create_backend_runtime_profile(
    backend: str,
    a1111_directory: Path,
    comfyui_directory: Path,
    runtime_directory_override: str | Path | None = None,
) -> BackendRuntimeProfile:
    normalized_backend = backend.strip().lower()
    backend_options = {
        "a1111": ("WebUI1111", Path(a1111_directory)),
        "comfyui": ("ComfyUI", Path(comfyui_directory)),
    }
    selected_backend = normalized_backend if normalized_backend in backend_options else "a1111"
    display_name, default_directory = backend_options[selected_backend]
    runtime_directory = (
        Path(runtime_directory_override).expanduser().resolve()
        if runtime_directory_override is not None
        else default_directory.resolve()
    )
    return BackendRuntimeProfile(selected_backend, display_name, runtime_directory)
