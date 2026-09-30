"""Common txt2img and img2img generation contract."""

from __future__ import annotations

from threading import Event
from typing import Protocol

from .image_to_image_request import ImageToImageRequest
from .text_to_image_request import TextToImageRequest


class ImageGenerationBackend(Protocol):
    def generate(self, request: TextToImageRequest, stop_event: Event | None = None) -> bytes | None:
        """Generate one image from text and return its encoded bytes."""
        ...

    def generate_from_image(self, request: ImageToImageRequest, stop_event: Event | None = None) -> bytes | None:
        """Generate one image from an input image and return encoded bytes."""
        ...
