"""ComfyUI txt2img API adapter."""

from __future__ import annotations

from threading import Event
from typing import Callable

from .comfy_ui_client import ComfyUIClient
from .text_to_image_request import TextToImageRequest


class ComfyUITextToImageBackend:
    def __init__(self, api_url: str, timeout: int, client_factory: Callable[..., ComfyUIClient] = ComfyUIClient) -> None:
        self.client = client_factory(api_url, timeout)

    def generate(self, request: TextToImageRequest, stop_event: Event | None = None) -> bytes | None:
        return self.client.txt2img(
            prompt=request.prompt,
            negative=request.negative,
            checkpoint=request.checkpoint,
            steps=request.steps,
            cfg=request.cfg,
            sampler=request.sampler,
            width=request.width,
            height=request.height,
            stop_event=stop_event,
            enable_hr=request.enable_hr,
            hr_scale=request.hr_scale,
            hr_upscaler=request.hr_upscaler,
            hr_second_pass_steps=request.hr_second_pass_steps,
            denoising_strength=request.denoising_strength,
            workflow_path=request.workflow_path,
            model_overrides=request.model_overrides,
        )
