"""Shared registrations for generation backends and their capabilities."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

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
from .image_generation_profile import (
    ImageGenerationProfile,
    create_a1111_image_generation_profile,
    create_comfyui_image_generation_profile,
)
from .image_generation_backend import ImageGenerationBackend
from .image_to_image_profile import (
    ImageToImageProfile,
    create_a1111_image_to_image_profile,
    create_comfyui_image_to_image_profile,
)

GenerationProfileKind = Literal["image_generation", "image_to_image"]
GenerationProfile = ImageGenerationProfile | ImageToImageProfile
GenerationProfileFactory = Callable[
    [str, str, Path, Path, str],
    GenerationProfile,
]


# {
#   責務: [GenerationBackendRegistration: 1 backendが提供するcatalog・adapter・profile・起動spec factoryを保持する]
#   フィールド: [catalog_factory: 共通候補catalog生成, adapter_factory: 画像生成adapter生成, profile_factories: 画面profile生成, launch_spec_factory: 任意のローカル起動spec生成]
#   処理: [backend登録の役割を名前付きimmutable contractとして提供する]
# }
@dataclass(frozen=True, slots=True)
class GenerationBackendRegistration:
    catalog_factory: Callable[[], GenerationBackendCatalog]
    adapter_factory: Callable[..., ImageGenerationBackend]
    profile_factories: Mapping[GenerationProfileKind, GenerationProfileFactory]
    launch_spec_factory: Callable[..., BackendLaunchSpec] | None


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


_GENERATION_BACKENDS: dict[str, GenerationBackendRegistration] = {
    "a1111": GenerationBackendRegistration(
        catalog_factory=A1111BackendCatalog,
        adapter_factory=_create_a1111_backend,
        profile_factories=MappingProxyType({
            "image_generation": create_a1111_image_generation_profile,
            "image_to_image": create_a1111_image_to_image_profile,
        }),
        launch_spec_factory=_create_a1111_launch_spec,
    ),
    "comfyui": GenerationBackendRegistration(
        catalog_factory=ComfyUIBackendCatalog,
        adapter_factory=_create_comfyui_backend,
        profile_factories=MappingProxyType({
            "image_generation": create_comfyui_image_generation_profile,
            "image_to_image": create_comfyui_image_to_image_profile,
        }),
        launch_spec_factory=_create_comfyui_launch_spec,
    ),
}

SUPPORTED_GENERATION_BACKENDS = tuple(_GENERATION_BACKENDS)
SUPPORTED_LAUNCH_BACKENDS = tuple(
    backend
    for backend, registration in _GENERATION_BACKENDS.items()
    if registration.launch_spec_factory is not None
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
        return registration.catalog_factory, registration.adapter_factory
    except KeyError as error:
        raise ValueError(f"Unsupported generation backend: {backend}") from error


# {
#   責務: [generation_backend_profile_factory: 登録済みbackendの画面既定値factoryを返す]
#   処理: [1: backendとprofile種別をregistryから検索する, 2: 対応するfactoryを返す]
#   引数: [backend: 生成backend ID, profile_kind: image_generationまたはimage_to_image]
#   戻り値: [GenerationProfileFactory: typed backend profile factory]
#   エラー: [ValueError: 未登録backendまたはprofile種別が指定された場合]
# }
def generation_backend_profile_factory(
    backend: str,
    profile_kind: GenerationProfileKind,
) -> GenerationProfileFactory:
    try:
        return _GENERATION_BACKENDS[backend].profile_factories[profile_kind]
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
        factory = _GENERATION_BACKENDS[backend].launch_spec_factory
        if factory is None:
            raise ValueError(f"Unsupported launch backend: {backend}")
        return factory
    except KeyError as error:
        raise ValueError(f"Unsupported launch backend: {backend}") from error
