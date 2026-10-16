"""Resolve the selected generation backend's runtime defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
#   責務: [_normalize_backend_id: 外部文字列を対応するgeneration backend IDへ正規化する]
#   処理: [前後空白と大小文字を正規化し, 許可済みIDだけを返す]
#   引数: [backend: 環境変数またはCLI由来のbackend文字列]
#   戻り値: [GenerationBackendId: 認識済みbackend ID, None: 未対応文字列]
# }
def _normalize_backend_id(backend: str) -> GenerationBackendId | None:
    normalized_backend = backend.strip().lower()
    if normalized_backend == "a1111":
        return "a1111"
    if normalized_backend == "comfyui":
        return "comfyui"
    return None


# {
#   責務: [create_backend_runtime_profile: 選択されたbackendのruntime profileを作る]
#   処理: [1: backend識別子を認識する, 2: 未対応時にfallback規則を適用する, 3: runtimeと表示名およびoverrideを選ぶ]
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
    backend_options: dict[GenerationBackendId, tuple[str, Path]] = {
        "a1111": ("WebUI1111", Path(a1111_directory)),
        "comfyui": ("ComfyUI", Path(comfyui_directory)),
    }
    selected_backend = _normalize_backend_id(backend)
    if selected_backend is None:
        if fallback_backend is None:
            raise ValueError(f"Unsupported runtime backend: {backend}")
        selected_backend = fallback_backend
    if selected_backend not in backend_options:
        raise ValueError(f"Unsupported fallback runtime backend: {selected_backend}")
    display_name, default_directory = backend_options[selected_backend]
    runtime_directory = (
        Path(runtime_directory_override).expanduser().resolve()
        if runtime_directory_override is not None
        else default_directory.resolve()
    )
    return BackendRuntimeProfile(selected_backend, display_name, runtime_directory)
