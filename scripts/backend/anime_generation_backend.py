"""Image-generation adapter that applies registered anime routing and prompt policies."""

from __future__ import annotations

from dataclasses import replace
from threading import Event

from comfyui_support_tools.shared.anime_generation import AnimeContentMode, AnimeIntent

from .anime_generation_policy import AnimePromptResolution, resolve_anime_generation
from .generation_capabilities import GenerationCapabilities
from .image_generation_backend import ImageGenerationBackend
from .image_to_image_request import ImageToImageRequest
from .text_to_image_request import TextToImageRequest


# {
#   責務: [AnimeGenerationBackend: apply anime family routing before a text-to-image backend call]
#   フィールド: [delegate backend, model catalog, intent, content profile, routing preference, last resolution]
#   処理: [resolve model and family policy then delegate a typed request without adding model-specific code to the generator]
# }
class AnimeGenerationBackend:
    # {
    #   責務: [__init__: configure a model-policy decorator for one generation adapter]
    #   処理: [bind an existing backend and the user's model/use-case constraints]
    #   引数: [backend: backend-neutral image adapter, model_catalog: installed model names, intent: anime use case, content_mode: optional profile, auto_route: route preference, has_explicit_model_overrides: explicit workflow model selection]
    #   戻り値: []
    # }
    def __init__(
        self,
        backend: ImageGenerationBackend,
        *,
        model_catalog: dict[str, list[str]],
        intent: AnimeIntent,
        content_mode: AnimeContentMode,
        auto_route: bool,
        has_explicit_model_overrides: bool,
    ) -> None:
        if not isinstance(intent, AnimeIntent) or not isinstance(content_mode, AnimeContentMode):
            raise ValueError("Anime generation controls must use declared enums")
        if auto_route and has_explicit_model_overrides:
            raise ValueError(
                "Anime auto-routing cannot override explicit ComfyUI node model selections"
            )
        self._backend = backend
        self._model_catalog = {key: list(values) for key, values in model_catalog.items()}
        self._intent = intent
        self._content_mode = content_mode
        self._auto_route = auto_route
        self._last_resolution: AnimePromptResolution | None = None
        self._prepared_request: TextToImageRequest | None = None

    # {
    #   責務: [capabilities: expose the wrapped backend's generation features]
    #   処理: [delegate declared capability metadata]
    #   引数: [self: model-policy adapter]
    #   戻り値: [GenerationCapabilities: wrapped backend capabilities]
    # }
    @property
    def capabilities(self) -> GenerationCapabilities:
        return self._backend.capabilities

    # {
    #   責務: [last_resolution: expose the most recent applied profile and prompt transformation]
    #   処理: [return the immutable result created for the preceding txt2img call]
    #   引数: [self: model-policy adapter]
    #   戻り値: [AnimePromptResolution | None: applied policy metadata]
    # }
    @property
    def last_resolution(self) -> AnimePromptResolution | None:
        return self._last_resolution

    # {
    #   責務: [generate: resolve anime model and prompt before delegating txt2img]
    #   処理: [apply the selected family profile to a copied request and preserve stop signaling]
    #   引数: [self: model-policy adapter, request: user generation request, stop_event: optional cancellation event]
    #   戻り値: [bytes | None: wrapped backend result]
    # }
    def generate(
        self, request: TextToImageRequest, stop_event: Event | None = None
    ) -> bytes | None:
        if request is self._prepared_request:
            self._prepared_request = None
            return self._backend.generate(request, stop_event=stop_event)
        return self._backend.generate(self.prepare_request(request), stop_event=stop_event)

    # {
    #   責務: [prepare_request: resolve model and prompt before validation or network work]
    #   処理: [apply one profile to a copied request and retain its immutable resolution metadata]
    #   引数: [self: model-policy adapter, request: original generation request]
    #   戻り値: [TextToImageRequest: prompt and checkpoint prepared for the wrapped backend]
    # }
    def prepare_request(self, request: TextToImageRequest) -> TextToImageRequest:
        self._last_resolution = resolve_anime_generation(
            request.checkpoint,
            request.prompt,
            request.negative,
            self._model_catalog,
            intent=self._intent,
            content_mode=self._content_mode,
            auto_route=self._auto_route,
        )
        self._prepared_request = replace(
            request,
            prompt=self._last_resolution.prompt,
            negative=self._last_resolution.negative_prompt,
            checkpoint=self._last_resolution.checkpoint,
        )
        return self._prepared_request

    # {
    #   責務: [generate_from_image: delegate img2img without text-to-image profile rewriting]
    #   処理: [preserve the source-image generation request unchanged]
    #   引数: [self: model-policy adapter, request: image-to-image request, stop_event: optional cancellation event]
    #   戻り値: [bytes | None: wrapped backend result]
    # }
    def generate_from_image(
        self, request: ImageToImageRequest, stop_event: Event | None = None
    ) -> bytes | None:
        return self._backend.generate_from_image(request, stop_event=stop_event)

    # {
    #   責務: [interrupt: delegate cancellation to the wrapped backend]
    #   処理: [forward the active generation interrupt request]
    #   引数: [self: model-policy adapter]
    #   戻り値: []
    # }
    def interrupt(self) -> None:
        self._backend.interrupt()
