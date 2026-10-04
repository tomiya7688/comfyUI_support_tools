"""ComfyUI txt2img and img2img API adapter."""

from __future__ import annotations

from threading import Event
from typing import Callable

from .comfy_ui_client import ComfyUIClient
from .image_to_image_request import ImageToImageRequest
from .generation_capabilities import GenerationCapabilities
from .text_to_image_request import TextToImageRequest


# {
# 責務: [ComfyUIImageGenerationBackend: 共通生成要求をComfyUI clientへ渡すadapter]
# フィールド: [client: ComfyUI APIとworkflowを扱うclient]
# 処理: [1: txt2img・img2imgの共通要求をclient引数へ写像する, 2: interruptを委譲する]
# }
class ComfyUIImageGenerationBackend:
    CAPABILITIES = GenerationCapabilities(frozenset({
        "txt2img", "img2img", "interrupt", "hires_fix", "model_catalog",
        "sampler_catalog", "upscaler_catalog", "workflow", "model_overrides",
    }))

    # {
    # 責務: [__init__: 接続設定を使ってComfyUI clientを生成する]
    # 処理: [1: factoryへAPI URLとtimeoutを渡してclientを保持する]
    # 引数: [api_url: ComfyUI API URL, timeout: 応答待ち時間, client_factory: client生成関数]
    # 戻り値: []
    # }
    def __init__(self, api_url: str, timeout: int, client_factory: Callable[..., ComfyUIClient] = ComfyUIClient) -> None:
        self.client = client_factory(api_url, timeout)

    # {
    # 責務: [capabilities: ComfyUI adapterの対応機能を公開する]
    # 処理: [1: クラス定義の固定機能集合を返す]
    # 引数: []
    # 戻り値: [workflow・model override等を含む対応機能]
    # }
    @property
    def capabilities(self) -> GenerationCapabilities:
        return self.CAPABILITIES

    # {
    # 責務: [interrupt: ComfyUI clientへ生成中断を委譲する]
    # 処理: [1: clientのinterrupt操作を呼び出す]
    # 引数: []
    # 戻り値: []
    # }
    def interrupt(self) -> None:
        self.client.interrupt()

    # {
    # 責務: [generate: text-to-image要求をComfyUI clientで生成する]
    # 処理: [1: requestの各条件をtxt2img引数へ写像する, 2: clientの生成結果を返す]
    # 引数: [request: promptと生成条件, stop_event: 任意の中断通知]
    # 戻り値: [生成画像のbytes、画像なしまたは中断時はNone]
    # }
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

    # {
    # 責務: [generate_from_image: image-to-image要求をComfyUI clientで生成する]
    # 処理: [1: requestの入力画像と条件をimg2img引数へ写像する, 2: clientの生成結果を返す]
    # 引数: [request: 入力画像と変換生成条件, stop_event: 任意の中断通知]
    # 戻り値: [生成画像のbytes、画像なしまたは中断時はNone]
    # }
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
