"""Shared registrations for generation backends and their capabilities."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .a1111_backend_catalog import A1111BackendCatalog
from .a1111_image_generation_backend import A1111ImageGenerationBackend
from .backend_launch_spec import (
    BackendLaunchSpec,
    _create_a1111_launch_spec,
    _create_comfyui_launch_spec,
)
from .comfy_ui_client import ComfyUIClient
from .comfyui_backend_catalog import ComfyUIBackendCatalog
from .comfyui_image_generation_backend import ComfyUIImageGenerationBackend
from .generation_backend_catalog import GenerationBackendCatalog
from .image_generation_profile import create_a1111_image_generation_profile, create_comfyui_image_generation_profile
from .image_generation_backend import ImageGenerationBackend
from .image_to_image_profile import create_a1111_image_to_image_profile, create_comfyui_image_to_image_profile


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
        dict[str, Callable[..., Any]],
        Callable[..., BackendLaunchSpec],
    ],
] = {
    "a1111": (
        A1111BackendCatalog,
        _create_a1111_backend,
        {
            "image_generation": create_a1111_image_generation_profile,
            "image_to_image": create_a1111_image_to_image_profile,
        },
        _create_a1111_launch_spec,
    ),
    "comfyui": (
        ComfyUIBackendCatalog,
        _create_comfyui_backend,
        {
            "image_generation": create_comfyui_image_generation_profile,
            "image_to_image": create_comfyui_image_to_image_profile,
        },
        _create_comfyui_launch_spec,
    ),
}

SUPPORTED_GENERATION_BACKENDS = tuple(_GENERATION_BACKENDS)
SUPPORTED_LAUNCH_BACKENDS = tuple(
    backend for backend, registration in _GENERATION_BACKENDS.items() if registration[3]
)


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
        registration = _GENERATION_BACKENDS[backend]
        return registration[0], registration[1]
    except KeyError as error:
        raise ValueError(f"Unsupported generation backend: {backend}") from error


# {
#   責務: [generation_backend_profile_factory: 登録済みbackendの画面既定値factoryを返す]
#   処理: [1: backendとprofile種別をregistryから検索する, 2: 対応するfactoryを返す]
#   引数: [backend: 生成backend ID, profile_kind: image_generationまたはimage_to_image]
#   戻り値: [Callable: backend固有profile factory]
#   エラー: [ValueError: 未登録backendまたはprofile種別が指定された場合]
# }
def generation_backend_profile_factory(backend: str, profile_kind: str) -> Callable[..., Any]:
    try:
        return _GENERATION_BACKENDS[backend][2][profile_kind]
    except KeyError as error:
        raise ValueError(
            f"Unsupported generation backend profile: {backend}/{profile_kind}"
        ) from error


# {
#   責務: [generation_backend_launch_spec_factory: 登録済みbackendの起動設定factoryを返す]
#   処理: [backend registryから起動spec factoryを検索して返す]
#   引数: [backend: 起動対象backend ID]
#   戻り値: [Callable: backend固有BackendLaunchSpec factory]
#   エラー: [ValueError: 未登録backendが指定された場合]
# }
def generation_backend_launch_spec_factory(backend: str) -> Callable[..., BackendLaunchSpec]:
    try:
        return _GENERATION_BACKENDS[backend][3]
    except KeyError as error:
        raise ValueError(f"Unsupported launch backend: {backend}") from error
