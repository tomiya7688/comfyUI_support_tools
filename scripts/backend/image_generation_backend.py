"""Common txt2img and img2img generation contract."""

from __future__ import annotations

from threading import Event
from typing import Protocol

from .image_to_image_request import ImageToImageRequest
from .generation_capabilities import GenerationCapabilities
from .text_to_image_request import TextToImageRequest


# {
# 責務: [ImageGenerationBackend: txt2img・img2imgと中断操作の共通契約を定義する]
# フィールド: []
# 処理: [1: 各backendが機能情報と生成操作を提供する]
# }
class ImageGenerationBackend(Protocol):

    # {
    # 責務: [capabilities: 実装backendが提供する機能を公開する契約]
    # 処理: [1: backend固有の機能集合を返す]
    # 引数: []
    # 戻り値: [対応機能を表すGenerationCapabilities]
    # }
    @property
    def capabilities(self) -> GenerationCapabilities:
        """Declare backend features without exposing its API details."""
        ...

    # {
    # 責務: [generate: テキスト生成操作のbackend契約]
    # 処理: [1: text-to-image要求を処理する]
    # 引数: [request: テキスト生成条件, stop_event: 任意の中断通知]
    # 戻り値: [生成画像bytesまたは画像なし・中断時のNone]
    # }
    def generate(self, request: TextToImageRequest, stop_event: Event | None = None) -> bytes | None:
        """Generate one image from text and return its encoded bytes."""
        ...

    # {
    # 責務: [generate_from_image: 画像入力付き生成操作のbackend契約]
    # 処理: [1: image-to-image要求を処理する]
    # 引数: [request: 入力画像と変換生成条件, stop_event: 任意の中断通知]
    # 戻り値: [生成画像bytesまたは画像なし・中断時のNone]
    # }
    def generate_from_image(self, request: ImageToImageRequest, stop_event: Event | None = None) -> bytes | None:
        """Generate one image from an input image and return encoded bytes."""
        ...

    # {
    # 責務: [interrupt: backendへ現在の生成中断を要求する契約]
    # 処理: [1: backend固有の中断操作を実行する]
    # 引数: []
    # 戻り値: []
    # }
    def interrupt(self) -> None:
        """Ask the backend to interrupt its active generation, if any."""
        ...
