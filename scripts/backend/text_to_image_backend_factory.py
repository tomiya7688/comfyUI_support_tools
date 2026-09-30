"""Construct the txt2img adapter for the selected generation service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .a1111_text_to_image_backend import A1111TextToImageBackend
from .comfyui_text_to_image_backend import ComfyUITextToImageBackend
from .text_to_image_backend import TextToImageBackend
from .comfy_ui_client import ComfyUIClient


def create_text_to_image_backend(
    backend: str,
    api_url: str,
    timeout: int,
    *,
    request_post: Callable[..., Any] | None = None,
    comfy_client_factory: Callable[..., ComfyUIClient] = ComfyUIClient,
) -> TextToImageBackend:
    if backend == "a1111":
        if request_post is None:
            raise ValueError("A1111 API用のPOST関数が必要です")
        return A1111TextToImageBackend(api_url, timeout, request_post)
    if backend == "comfyui":
        return ComfyUITextToImageBackend(api_url, timeout, comfy_client_factory)
    raise ValueError(f"Unsupported generation backend: {backend}")
