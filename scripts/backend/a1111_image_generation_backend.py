"""A1111 txt2img and img2img API adapter."""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from .image_to_image_request import ImageToImageRequest
from .generation_capabilities import GenerationCapabilities
from .text_to_image_request import TextToImageRequest


# {
# 責務: [A1111ImageGenerationBackend: 共通生成要求をAUTOMATIC1111 REST APIへ変換する]
# フィールド: [api_url: 生成APIのURL, timeout: API応答待ち時間, request_post: HTTP POST関数]
# 処理: [1: txt2img・img2img要求をAPI payloadに変換する, 2: 応答画像をbytesへ戻す, 3: interruptを送る]
# }
class A1111ImageGenerationBackend:
    CAPABILITIES = GenerationCapabilities(frozenset({
        "txt2img", "img2img", "interrupt", "hires_fix", "model_catalog",
        "sampler_catalog", "upscaler_catalog", "vae_override",
    }))

    # {
    # 責務: [__init__: AUTOMATIC1111接続設定とHTTP依存を保持する]
    # 処理: [1: API URL、timeout、POST関数を初期状態へ設定する]
    # 引数: [api_url: 生成API URL, timeout: 応答待ち時間, request_post: HTTP POST関数]
    # 戻り値: []
    # }
    def __init__(self, api_url: str, timeout: int, request_post: Callable[..., Any]) -> None:
        self.api_url = api_url
        self.timeout = timeout
        self.request_post = request_post

    # {
    # 責務: [capabilities: AUTOMATIC1111 adapterの対応機能を公開する]
    # 処理: [1: クラス定義の固定機能集合を返す]
    # 引数: []
    # 戻り値: [生成・interrupt・hires等の対応機能]
    # }
    @property
    def capabilities(self) -> GenerationCapabilities:
        return self.CAPABILITIES

    # {
    # 責務: [interrupt: AUTOMATIC1111の実行中生成へ中断要求を送る]
    # 処理: [1: API rootを求める, 2: interrupt endpointへPOSTする, 3: HTTP errorを検査する]
    # 引数: []
    # 戻り値: []
    # }
    def interrupt(self) -> None:
        api_root = self.api_url.split("/sdapi/", 1)[0].rstrip("/")
        response = self.request_post(f"{api_root}/sdapi/v1/interrupt", timeout=10)
        response.raise_for_status()

    # {
    # 責務: [generate: text-to-image要求をAUTOMATIC1111で1枚生成する]
    # 処理: [1: 中断済み要求を除外する, 2: requestをtxt2img payloadへ変換する, 3: API画像をbase64 decodeする]
    # 引数: [request: promptと生成条件, stop_event: 任意の中断通知]
    # 戻り値: [生成画像のbytes、画像なしまたは中断時はNone]
    # }
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

    # {
    # 責務: [generate_from_image: 画像入力付き要求をAUTOMATIC1111で変換生成する]
    # 処理: [1: 中断済み要求を除外する, 2: 入力画像と生成条件をimg2img payloadへ変換する, 3: API画像をdecodeする]
    # 引数: [request: 入力画像と変換生成条件, stop_event: 任意の中断通知]
    # 戻り値: [生成画像のbytes、画像なしまたは中断時はNone]
    # }
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
