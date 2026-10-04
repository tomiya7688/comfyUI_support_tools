"""Create a catalog adapter for one selected image-generation backend."""

from __future__ import annotations

from .a1111_backend_catalog import A1111BackendCatalog
from .comfyui_backend_catalog import ComfyUIBackendCatalog
from .generation_backend_catalog import GenerationBackendCatalog


# {
# 責務: [create_generation_backend_catalog: 指定バックエンドに対応するカタログを生成する]
# 処理: [1: backend名に対応するカタログ実装を選ぶ, 2: 未対応名ならエラーを返す]
# 引数: [backend: カタログを生成するバックエンド名]
# 戻り値: [選択したGenerationBackendCatalog実装]
# }
# {
# 責務: [create_generation_backend_catalog: 指定backendに対応するカタログを生成する]
# 処理: [1: backend名に対応する実装を選ぶ, 2: 未対応名ならエラーを返す]
# 引数: [backend: カタログを生成するbackend名]
# 戻り値: [選択したGenerationBackendCatalog実装]
# }
def create_generation_backend_catalog(backend: str) -> GenerationBackendCatalog:
    if backend == "a1111":
        return A1111BackendCatalog()
    if backend == "comfyui":
        return ComfyUIBackendCatalog()
    raise ValueError(f"Unsupported generation backend: {backend}")
