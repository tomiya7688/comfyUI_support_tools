"""Construct the image-generation adapter for the selected backend."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .a1111_image_generation_backend import A1111ImageGenerationBackend
from .comfyui_image_generation_backend import ComfyUIImageGenerationBackend
from .comfy_ui_client import ComfyUIClient
from .image_generation_backend import ImageGenerationBackend


def create_image_generation_backend(
    backend: str,
    api_url: str,
    timeout: int,
    *,
    request_post: Callable[..., Any] | None = None,
    comfy_client_factory: Callable[..., ComfyUIClient] = ComfyUIClient,
) -> ImageGenerationBackend:
    if backend == "a1111":
        if request_post is None:
            raise ValueError("A1111 API用のPOST関数が必要です")
        return A1111ImageGenerationBackend(api_url, timeout, request_post)
    if backend == "comfyui":
        return ComfyUIImageGenerationBackend(api_url, timeout, comfy_client_factory)
    raise ValueError(f"Unsupported generation backend: {backend}")
