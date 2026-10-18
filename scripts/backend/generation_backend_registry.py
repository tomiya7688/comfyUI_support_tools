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
from .generation_backend_types import GenerationBackendId
from .generation_profile_inputs import GenerationProfileInputs
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
GenerationProfileFactory = Callable[[GenerationProfileInputs], GenerationProfile]


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


_GENERATION_BACKENDS: dict[GenerationBackendId, GenerationBackendRegistration] = {
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

SUPPORTED_GENERATION_BACKENDS: tuple[GenerationBackendId, ...] = tuple(_GENERATION_BACKENDS)
SUPPORTED_LAUNCH_BACKENDS: tuple[GenerationBackendId, ...] = tuple(
    backend
    for backend, registration in _GENERATION_BACKENDS.items()
    if registration.launch_spec_factory is not None
)


# {
#   責務: [create_registered_generation_backend_catalog: 登録backendの共通catalogを生成する]
#   処理: [1: 登録済みbackendを検索する, 2: 内部catalog factoryを呼び出して返す]
#   引数: [backend: 生成backend ID]
#   戻り値: [GenerationBackendCatalog: backend別候補取得契約]
#   エラー: [ValueError: 未登録backendが指定された場合]
# }
def create_registered_generation_backend_catalog(
    backend: GenerationBackendId,
) -> GenerationBackendCatalog:
    try:
        return _GENERATION_BACKENDS[backend].catalog_factory()
    except KeyError as error:
        raise ValueError(f"Unsupported generation backend: {backend}") from error


# {
#   責務: [create_registered_image_generation_backend: 登録backendの画像生成adapterを生成する]
#   処理: [1: 登録済みbackendを検索する, 2: 内部adapter factoryへ共通引数を渡す]
#   引数: [backend: 生成backend ID, api_url: 生成API URL, timeout: API timeout秒, request_post: optional HTTP POST関数, comfy_client_factory: ComfyUI client factory]
#   戻り値: [ImageGenerationBackend: backend中立な生成adapter]
#   エラー: [ValueError: 未登録backendまたは必須接続関数が不足した場合]
# }
def create_registered_image_generation_backend(
    backend: GenerationBackendId,
    api_url: str,
    timeout: int,
    *,
    request_post: Callable[..., Any] | None = None,
    comfy_client_factory: Callable[..., ComfyUIClient] = ComfyUIClient,
) -> ImageGenerationBackend:
    try:
        factory = _GENERATION_BACKENDS[backend].adapter_factory
    except KeyError as error:
        raise ValueError(f"Unsupported generation backend: {backend}") from error
    return factory(
        api_url,
        timeout,
        request_post=request_post,
        comfy_client_factory=comfy_client_factory,
    )


# {
#   責務: [create_generation_profile: 登録backendと用途から共通生成profileを構築する]
#   処理: [1: 登録済みbackendの対応profile factoryを検索する, 2: 名前付き入力を渡してprofileを返す]
#   引数: [backend: 生成backend ID, profile_kind: profile用途, inputs: 共通生成設定入力]
#   戻り値: [GenerationProfile: 画像生成またはImg2Imgのbackend-neutral profile]
#   エラー: [ValueError: 未登録backendまたはprofile用途が指定された場合]
# }
def create_generation_profile(
    backend: GenerationBackendId,
    profile_kind: GenerationProfileKind,
    inputs: GenerationProfileInputs,
) -> GenerationProfile:
    try:
        factory = _GENERATION_BACKENDS[backend].profile_factories[profile_kind]
    except KeyError as error:
        raise ValueError(
            f"Unsupported generation backend profile: {backend}/{profile_kind}"
        ) from error
    return factory(inputs)


# {
#   責務: [create_registered_backend_launch_spec: 登録backendの起動設定を生成する]
#   処理: [1: 起動可能なbackend登録を検索する, 2: 内部factoryへ共通設定を渡しspecを返す]
#   引数: [backend: 起動対象backend ID, a1111_api_url: A1111 API URL, comfyui_api_url: ComfyUI API URL, checkpoints_dir: checkpoint共有directory, models_dir: 共有model directory]
#   戻り値: [BackendLaunchSpec: 起動に必要なbackend固有設定]
#   エラー: [ValueError: 未登録または起動非対応backendが指定された場合]
# }
def create_registered_backend_launch_spec(
    backend: GenerationBackendId,
    a1111_api_url: str,
    comfyui_api_url: str,
    checkpoints_dir: Path,
    models_dir: Path,
) -> BackendLaunchSpec:
    try:
        factory = _GENERATION_BACKENDS[backend].launch_spec_factory
        if factory is None:
            raise ValueError(f"Unsupported launch backend: {backend}")
        return factory(a1111_api_url, comfyui_api_url, checkpoints_dir, models_dir)
    except KeyError as error:
        raise ValueError(f"Unsupported launch backend: {backend}") from error
