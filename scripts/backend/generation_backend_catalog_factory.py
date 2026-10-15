"""Create a catalog adapter for one selected image-generation backend."""

from __future__ import annotations

from .generation_backend_catalog import GenerationBackendCatalog
from .generation_backend_types import GenerationBackendId
from .generation_backend_registry import generation_backend_factories


# {
#   責務: [create_generation_backend_catalog: backendの共通catalog adapterを作成する]
#   処理: [1: registryからcatalog factoryを取得する, 2: catalog instanceを返す]
#   引数: [backend: 生成backend ID]
#   戻り値: [GenerationBackendCatalog: backend別候補取得契約]
#   エラー: [ValueError: 未登録backendが指定された場合]
# }
def create_generation_backend_catalog(backend: GenerationBackendId) -> GenerationBackendCatalog:
    catalog_factory, _ = generation_backend_factories(backend)
    return catalog_factory()
