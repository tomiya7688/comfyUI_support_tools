"""Common txt2img and img2img generation contract."""

from __future__ import annotations

from threading import Event
from typing import Protocol

from .image_to_image_request import ImageToImageRequest
from .generation_capabilities import GenerationCapabilities
from .text_to_image_request import TextToImageRequest


# {
#   責務: [ImageGenerationBackend: txt2img and img2img backend implementationsのshared protocolを定義する]
#   処理: [declare capability, generation, and interrupt contracts without implementation state]
#   フィールド: [capabilities, generate, generate_from_image, interrupt protocol members]
# }
class ImageGenerationBackend(Protocol):
    # {
    #   責務: [capabilities: supported backend featuresをdeclareするprotocol property]
    #   処理: [expose GenerationCapabilities without provider-specific API]
    #   引数: [なし]
    #   戻り値: [GenerationCapabilities]
    # }
    @property
    def capabilities(self) -> GenerationCapabilities:
        """Declare backend features without exposing its API details."""
        ...

    # {
    #   責務: [generate: text-to-image requestをencoded image bytesへprocessするprotocol method]
    #   処理: [return bytes or None and optionally honor cancellation event]
    #   引数: [request, stop_event]
    #   戻り値: [bytes | None]
    # }
    def generate(self, request: TextToImageRequest, stop_event: Event | None = None) -> bytes | None:
        """Generate one image from text and return its encoded bytes."""
        ...

    # {
    #   責務: [generate_from_image: image-to-image requestをencoded image bytesへprocessするprotocol method]
    #   処理: [return bytes or None and optionally honor cancellation event]
    #   引数: [request, stop_event]
    #   戻り値: [bytes | None]
    # }
    def generate_from_image(self, request: ImageToImageRequest, stop_event: Event | None = None) -> bytes | None:
        """Generate one image from an input image and return encoded bytes."""
        ...

    # {
    #   責務: [interrupt: active generation interruptionをrequestするprotocol method]
    #   処理: [ask backend to stop current work when supported]
    #   引数: [なし]
    #   戻り値: [None]
    # }
    def interrupt(self) -> None:
        """Ask the backend to interrupt its active generation, if any."""
        ...
