"""ComfyUI txt2img and img2img API adapter."""

from __future__ import annotations

from threading import Event
from typing import Callable

from .comfy_ui_client import ComfyUIClient
from .image_to_image_request import ImageToImageRequest
from .generation_capabilities import GenerationCapabilities
from .text_to_image_request import TextToImageRequest


class ComfyUIImageGenerationBackend:
    CAPABILITIES = GenerationCapabilities(frozenset({
        "txt2img", "img2img", "interrupt", "hires_fix", "model_catalog",
        "sampler_catalog", "upscaler_catalog", "workflow", "model_overrides",
    }))

    def __init__(self, api_url: str, timeout: int, client_factory: Callable[..., ComfyUIClient] = ComfyUIClient) -> None:
        self.client = client_factory(api_url, timeout)

    @property
    def capabilities(self) -> GenerationCapabilities:
        return self.CAPABILITIES

    def interrupt(self) -> None:
        self.client.interrupt()

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
            vae_name=request.vae_name,
        )

    def generate_from_image(self, request: ImageToImageRequest, stop_event: Event | None = None) -> bytes | None:
        return self.client.img2img(
            image_path=request.image_path,
            prompt=request.prompt,
            negative=request.negative,
            checkpoint=request.checkpoint,
            steps=request.steps,
            cfg=request.cfg,
            sampler=request.sampler,
            denoise=request.denoise,
            width=request.width,
            height=request.height,
            vae_name=request.vae_name,
            stop_event=stop_event,
        )
