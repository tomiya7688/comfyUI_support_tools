"""ComfyUI txt2img and img2img API adapter."""

from __future__ import annotations

from threading import Event
from typing import Callable

from .comfy_ui_client import ComfyUIClient
from .image_to_image_request import ImageToImageRequest
from .generation_capabilities import GenerationCapabilities
from .text_to_image_request import TextToImageRequest


# {
#   責務: [ComfyUIImageGenerationBackend: ComfyUI clientをbackend-neutral generation interfaceとして公開する]
#   処理: [txt2img/img2img, interrupt, workflow, override capabilitiesを委譲する]
#   フィールド: [client instance and CAPABILITIES]
# }
# {
#   責務: [ComfyUIImageGenerationBackend: ComfyUI clientをbackend-neutral generation interfaceとして公開する]
#   処理: [txt2img/img2img, interrupt, workflow, override capabilitiesを委譲する]
#   フィールド: [client instance and CAPABILITIES]
# }
class ComfyUIImageGenerationBackend:
    CAPABILITIES = GenerationCapabilities(frozenset({
        "txt2img", "img2img", "interrupt", "hires_fix", "model_catalog",
        "sampler_catalog", "upscaler_catalog", "workflow", "model_overrides",
    }))

    # {
    #   責務: [__init__: ComfyUI API用clientをfactoryから構築する]
    #   処理: [api_url and timeoutをclient factoryへ渡して保存する]
    #   引数: [api_url, timeout, client_factory]
    #   戻り値: [None]
    # }
    # {
    #   責務: [__init__: ComfyUI API用clientをfactoryから構築する]
    #   処理: [api_url and timeoutをclient factoryへ渡して保存する]
    #   引数: [api_url, timeout, client_factory]
    #   戻り値: [None]
    # }
    def __init__(self, api_url: str, timeout: int, client_factory: Callable[..., ComfyUIClient] = ComfyUIClient) -> None:
        self.client = client_factory(api_url, timeout)

    # {
    #   責務: [capabilities: ComfyUI backend capability declarationを返す]
    #   処理: [class-level immutable capability setを公開する]
    #   引数: [なし]
    #   戻り値: [GenerationCapabilities]
    # }
    # {
    #   責務: [capabilities: ComfyUI backend capability declarationを返す]
    #   処理: [class-level immutable capability setを公開する]
    #   引数: [なし]
    #   戻り値: [GenerationCapabilities]
    # }
    @property
    def capabilities(self) -> GenerationCapabilities:
        return self.CAPABILITIES

    # {
    #   責務: [interrupt: ComfyUI active generationへinterrupt requestを委譲する]
    #   処理: [client.interruptを呼び出す]
    #   引数: [なし]
    #   戻り値: [None]
    # }
    # {
    #   責務: [interrupt: ComfyUI active generationへinterrupt requestを委譲する]
    #   処理: [client.interruptを呼び出す]
    #   引数: [なし]
    #   戻り値: [None]
    # }
    def interrupt(self) -> None:
        self.client.interrupt()

    # {
    #   責務: [generate: backend-neutral txt2img requestをComfyUI clientへ委譲する]
    #   処理: [request fields and stop eventをclient.txt2imgへ転送する]
    #   引数: [request, stop_event]
    #   戻り値: [bytes | None]
    # }
    # {
    #   責務: [generate: backend-neutral txt2img requestをComfyUI clientへ委譲する]
    #   処理: [request fields and stop eventをclient.txt2imgへ転送する]
    #   引数: [request, stop_event]
    #   戻り値: [bytes | None]
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
    #   責務: [generate_from_image: backend-neutral img2img requestをComfyUI clientへ委譲する]
    #   処理: [image path, generation parameters, VAE and stop eventをclient.img2imgへ転送する]
    #   引数: [request, stop_event]
    #   戻り値: [bytes | None]
    # }
    # {
    #   責務: [generate_from_image: backend-neutral img2img requestをComfyUI clientへ委譲する]
    #   処理: [image path, generation parameters, VAE and stop eventをclient.img2imgへ転送する]
    #   引数: [request, stop_event]
    #   戻り値: [bytes | None]
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
