"""A1111/ComfyUI img2img adapter for canonical-anchored sprite frame drafts."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

from PIL import Image

from comfyui_support_tools.shared.pixel_sprite.contracts import SpriteFrameSpec

from ..context import create_configured_image_generation_backend
from .image_to_image_request import ImageToImageRequest


# {
# 責務: [ImageToSpriteFrameGenerator: shared img2img backendからsprite pose frame候補を作る]
# フィールド: [api connection, model settings, denoise budget]
# 処理: [canonical imageをtemporary inputにしてdirection/action条件を追加する]
# }
class ImageToSpriteFrameGenerator:
    # {
    # 責務: [__init__: configured image-generation backendとimg2img settingsを保持する]
    # 処理: [backendを遅延生成しhost injectionにも対応する]
    # 引数: [self: adapter, api_url: backend endpoint, timeout: request timeout, checkpoint: model id, steps/cfg/sampler: generation settings, denoise: structure-preservation strength, backend: optional generation backend]
    # 戻り値: []
    # }
    def __init__(
        self,
        api_url: str,
        timeout: int,
        *,
        checkpoint: str = "",
        steps: int = 24,
        cfg: float = 6.0,
        sampler: str = "Euler a",
        denoise: float = 0.45,
        backend: object | None = None,
    ) -> None:
        if steps < 1 or steps > 100:
            raise ValueError("steps must be between 1 and 100")
        if not 0 <= denoise <= 1:
            raise ValueError("denoise must be between 0 and 1")
        self.api_url = api_url
        self.timeout = timeout
        self.checkpoint = checkpoint
        self.steps = steps
        self.cfg = cfg
        self.sampler = sampler
        self.denoise = denoise
        self._backend = backend

    # {
    # 責務: [generate: canonical anchorから方向/action別のimg2img frameを生成する]
    # 処理: [1: canonicalを一時PNGへ保存する, 2: pose prompt付きimg2img要求を送る, 3: result imageをdecodeする]
    # 引数: [self: adapter, canonical: anchor sprite, spec: requested frame pose, prompt: base character description]
    # 戻り値: [Image: decoded candidate frame]
    # }
    def generate(self, canonical: Image.Image, spec: SpriteFrameSpec, prompt: str) -> Image.Image:
        if canonical.width * canonical.height > 50_000_000:
            raise ValueError("canonical sprite exceeds 50 megapixel limit")
        backend = self._get_backend()
        if not backend.capabilities.supports("img2img"):
            raise ValueError("selected backend does not support img2img sprite generation")
        with tempfile.TemporaryDirectory(prefix="pixel-sprite-frame-") as temporary:
            image_path = Path(temporary) / "canonical.png"
            canonical.save(image_path, format="PNG")
            conditions = [
                prompt.strip(),
                "same canonical pixel-art character and outfit",
                f"{spec.direction.value.replace('_', ' ')} direction",
                f"{spec.action} animation pose, frame {spec.index + 1} of {spec.frame_count}",
                spec.pose_instruction.strip(),
                "preserve sprite proportions and pixel-art outline",
            ]
            request = ImageToImageRequest(
                image_path=image_path,
                prompt=", ".join(item for item in conditions if item),
                negative="different character, changed outfit, extra limbs, text, blurry pixels",
                checkpoint=self.checkpoint,
                steps=self.steps,
                cfg=self.cfg,
                sampler=self.sampler,
                denoise=self.denoise,
                width=canonical.width,
                height=canonical.height,
            )
            image_bytes = backend.generate_from_image(request)
        if not image_bytes:
            raise RuntimeError(
                f"backend returned no sprite image for {spec.action}/{spec.direction.value}"
            )
        try:
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.load()
                if image.width * image.height > 50_000_000:
                    raise ValueError("generated sprite exceeds 50 megapixel limit")
                return image.convert("RGBA")
        except (OSError, ValueError) as error:
            raise ValueError(f"backend returned an invalid sprite image: {error}") from error

    # {
    # 責務: [_get_backend: configured backendをlazy resolveする]
    # 処理: [1: existing injected backendを返す, 2: connection factoryを呼ぶ]
    # 引数: [self: adapter]
    # 戻り値: [ImageGenerationBackend: txt2img/img2img adapter]
    # }
    def _get_backend(self):
        if self._backend is None:
            self._backend = create_configured_image_generation_backend(self.api_url, self.timeout)
        return self._backend
