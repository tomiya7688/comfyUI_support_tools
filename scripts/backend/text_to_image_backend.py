"""Contract for backend-specific txt2img request adapters."""

from __future__ import annotations

from threading import Event
from typing import Protocol

from .text_to_image_request import TextToImageRequest


class TextToImageBackend(Protocol):
    def generate(self, request: TextToImageRequest, stop_event: Event | None = None) -> bytes | None:
        """Generate one image and return its encoded bytes, if available."""
        ...
