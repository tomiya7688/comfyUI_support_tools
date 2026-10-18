"""Create a catalog adapter for one selected image-generation backend."""

from __future__ import annotations

from .generation_backend_catalog import GenerationBackendCatalog
from .generation_backend_types import GenerationBackendId
from .generation_backend_registry import create_registered_generation_backend_catalog


# {
#   責務: [create_generation_backend_catalog: backendの共通catalog adapterを作成する]
#   処理: [registryから選択backendのcatalog instanceを受け取る]
#   引数: [backend: 生成backend ID]
#   戻り値: [GenerationBackendCatalog: backend別候補取得契約]
#   エラー: [ValueError: 未登録backendが指定された場合]
# }
def create_generation_backend_catalog(backend: GenerationBackendId) -> GenerationBackendCatalog:
    return create_registered_generation_backend_catalog(backend)
