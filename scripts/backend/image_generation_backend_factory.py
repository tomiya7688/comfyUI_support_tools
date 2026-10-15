"""Construct the image-generation adapter for the selected backend."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .comfy_ui_client import ComfyUIClient
from .generation_backend_registry import generation_backend_factories
from .generation_backend_types import GenerationBackendId
from .image_generation_backend import ImageGenerationBackend


# {
#   責務: [create_image_generation_backend: registryから選択backendの画像生成adapterを作成する]
#   処理: [1: 登録済みadapter factoryを取得する, 2: API URL・timeout・接続関数を渡す]
#   引数: [backend: 生成backend ID, api_url: 生成API URL, timeout: API timeout秒, request_post: optional HTTP POST関数, comfy_client_factory: ComfyUI client factory]
#   戻り値: [ImageGenerationBackend: backend中立な生成adapter]
#   エラー: [ValueError: 未登録backendまたは必須接続関数が不足した場合]
# }
def create_image_generation_backend(
    backend: GenerationBackendId,
    api_url: str,
    timeout: int,
    *,
    request_post: Callable[..., Any] | None = None,
    comfy_client_factory: Callable[..., ComfyUIClient] = ComfyUIClient,
) -> ImageGenerationBackend:
    _, image_generation_factory = generation_backend_factories(backend)
    return image_generation_factory(
        api_url,
        timeout,
        request_post=request_post,
        comfy_client_factory=comfy_client_factory,
    )
