"""Shared registrations for image-generation adapters and their catalogs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .a1111_backend_catalog import A1111BackendCatalog
from .a1111_image_generation_backend import A1111ImageGenerationBackend
from .comfyui_backend_catalog import ComfyUIBackendCatalog
from .comfyui_image_generation_backend import ComfyUIImageGenerationBackend
from .comfy_ui_client import ComfyUIClient
from .generation_backend_catalog import GenerationBackendCatalog
from .image_generation_backend import ImageGenerationBackend


# {
#   責務: [_create_a1111_backend: 共通引数からA1111 adapterを生成する]
#   処理: [1: 必須のHTTP POST関数を検証する, 2: A1111 adapterを返す]
#   引数: [api_url: API URL, timeout: API timeout秒, request_post: HTTP POST関数, comfy_client_factory: 互換用client factory]
#   戻り値: [A1111ImageGenerationBackend: A1111生成adapter]
#   エラー: [ValueError: request_postが指定されていない場合]
# }
def _create_a1111_backend(
    api_url: str,
    timeout: int,
    *,
    request_post: Callable[..., Any] | None,
    comfy_client_factory: Callable[..., ComfyUIClient],
) -> ImageGenerationBackend:
    if request_post is None:
        raise ValueError("A1111 API用のPOST関数が必要です")
    return A1111ImageGenerationBackend(api_url, timeout, request_post)


# {
#   責務: [_create_comfyui_backend: 共通引数からComfyUI adapterを生成する]
#   処理: [ComfyUI client factoryを使うadapterを返す]
#   引数: [api_url: API URL, timeout: API timeout秒, request_post: 未使用の互換引数, comfy_client_factory: ComfyUI client factory]
#   戻り値: [ComfyUIImageGenerationBackend: ComfyUI生成adapter]
# }
def _create_comfyui_backend(
    api_url: str,
    timeout: int,
    *,
    request_post: Callable[..., Any] | None,
    comfy_client_factory: Callable[..., ComfyUIClient],
) -> ImageGenerationBackend:
    return ComfyUIImageGenerationBackend(api_url, timeout, comfy_client_factory)


_GENERATION_BACKENDS: dict[
    str,
    tuple[
        Callable[[], GenerationBackendCatalog],
        Callable[..., ImageGenerationBackend],
    ],
] = {
    "a1111": (A1111BackendCatalog, _create_a1111_backend),
    "comfyui": (ComfyUIBackendCatalog, _create_comfyui_backend),
}

SUPPORTED_GENERATION_BACKENDS = tuple(_GENERATION_BACKENDS)


# {
#   責務: [generation_backend_factories: backend共通catalogと生成adapterのfactoryを返す]
#   処理: [1: 登録済みbackendを検索する, 2: 共通factory組を返す]
#   引数: [backend: 生成backend ID]
#   戻り値: [tuple: catalog factoryとimage-generation adapter factory]
#   エラー: [ValueError: 未登録backendが指定された場合]
# }
def generation_backend_factories(
    backend: str,
) -> tuple[
    Callable[[], GenerationBackendCatalog],
    Callable[..., ImageGenerationBackend],
]:
    try:
        return _GENERATION_BACKENDS[backend]
    except KeyError as error:
        raise ValueError(f"Unsupported generation backend: {backend}") from error
