"""A1111 txt2img and img2img API adapter."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from .image_to_image_request import ImageToImageRequest
from .generation_capabilities import GenerationCapabilities
from .text_to_image_request import TextToImageRequest


# {
#   責務: [A1111ImageGenerationBackend: A1111 API経由で画像生成要求を実行する]
#   フィールド: [CAPABILITIES: A1111 adapterが提供する機能一覧]
#   処理: [A1111 APIのtxt2img/img2img等を共通interfaceで提供する]
# }
class A1111ImageGenerationBackend:
    CAPABILITIES = GenerationCapabilities(
        frozenset(
            {
                "txt2img",
                "img2img",
                "interrupt",
                "hires_fix",
                "model_catalog",
                "sampler_catalog",
                "upscaler_catalog",
                "vae_override",
                "nudenet_mosaic",
            }
        )
    )

    def __init__(self, api_url: str, timeout: int, request_post: Callable[..., Any]) -> None:
        self.api_url = api_url
        self.timeout = timeout
        self.request_post = request_post

    @property
    def capabilities(self) -> GenerationCapabilities:
        return self.CAPABILITIES

    def interrupt(self) -> None:
        api_root = self.api_url.split("/sdapi/", 1)[0].rstrip("/")
        response = self.request_post(f"{api_root}/sdapi/v1/interrupt", timeout=10)
        response.raise_for_status()

    def generate(self, request: TextToImageRequest, stop_event=None) -> bytes | None:
        if stop_event is not None and stop_event.is_set():
            return None
        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative,
            "steps": request.steps,
            "cfg_scale": request.cfg,
            "enable_hr": request.enable_hr,
            "hr_scale": request.hr_scale,
            "hr_upscaler": request.hr_upscaler,
            "hr_second_pass_steps": request.hr_second_pass_steps,
            "denoising_strength": request.denoising_strength,
            "width": request.width,
            "height": request.height,
            "sampler_index": request.sampler,
            "save_images": request.save_images,
            "override_settings": {"sd_model_checkpoint": request.checkpoint},
        }
        if request.vae_name:
            payload["override_settings"]["sd_vae"] = request.vae_name
        elif request.use_model_vae:
            payload["override_settings"]["sd_vae"] = "Automatic"
        response = self.request_post(self.api_url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        images = response.json().get("images", [])
        return base64.b64decode(images[0]) if images else None

    def generate_from_image(self, request: ImageToImageRequest, stop_event=None) -> bytes | None:
        if stop_event is not None and stop_event.is_set():
            return None
        payload = {
            "prompt": request.prompt,
            "negative_prompt": request.negative,
            "init_images": [base64.b64encode(request.image_path.read_bytes()).decode("ascii")],
            "steps": request.steps,
            "cfg_scale": request.cfg,
            "width": request.width,
            "height": request.height,
            "denoising_strength": request.denoise,
            "sampler_index": request.sampler,
            "override_settings": {"sd_model_checkpoint": request.checkpoint},
        }
        if request.vae_name:
            payload["override_settings"]["sd_vae"] = request.vae_name
        response = self.request_post(self.api_url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        images = response.json().get("images", [])
        return base64.b64decode(images[0]) if images else None
