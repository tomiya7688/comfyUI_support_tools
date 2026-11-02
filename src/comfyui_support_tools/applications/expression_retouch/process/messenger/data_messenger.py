"""Process-side boundary for Expression Retouch data operations."""

from pathlib import Path
from typing import Any, Protocol

from comfyui_support_tools.shared.contracts.expression_retouch import (
    DetectedFace,
    FaceAnalysis,
    FacePart,
)


# {
#   責務: [ExpressionRetouchDataPort: describe Data operations consumed by Process]
#   フィールド: [normalize, analyze, mask, measure, composite, save_run calls]
#   処理: [keep Process independent of image-storage implementations]
# }
class ExpressionRetouchDataPort(Protocol):
    # {
    #   責務: [normalize: normalize the source image]
    #   処理: [return orientation-corrected PNG bytes]
    #   引数: [source: encoded image]
    #   戻り値: [bytes: normalized image]
    # }
    def normalize(self, source: bytes) -> bytes: ...

    # {
    #   責務: [analyze: detect targetable faces]
    #   処理: [return ordered face detections and limitations]
    #   引数: [source: normalized image]
    #   戻り値: [FaceAnalysis: detector result]
    # }
    def analyze(self, source: bytes) -> FaceAnalysis: ...

    # {
    #   責務: [mask: build one selected local mask]
    #   処理: [return a feathered grayscale image mask]
    #   引数: [size: source dimensions, face: selected face, parts: regions, manual: optional user mask]
    #   戻り値: [bytes: mask image]
    # }
    def mask(
        self,
        size: tuple[int, int],
        face: DetectedFace,
        parts: tuple[FacePart, ...],
        manual: bytes | None,
    ) -> bytes: ...

    # {
    #   責務: [measure: report local preservation proxies]
    #   処理: [compare source/candidate pixels against the edit mask]
    #   引数: [source: original, candidate: backend output, mask: allowed region]
    #   戻り値: [tuple: identity proxy, locality, limitations]
    # }
    def measure(self, source: bytes, candidate: bytes, mask: bytes): ...

    # {
    #   責務: [composite: preserve unmasked source pixels]
    #   処理: [apply the mask-based alpha composite]
    #   引数: [source: original, candidate: backend output, mask: allowed region]
    #   戻り値: [bytes: locally composited image]
    # }
    def composite(self, source: bytes, candidate: bytes, mask: bytes) -> bytes: ...

    # {
    #   責務: [save_run: persist an immutable edit run]
    #   処理: [store source, mask, candidates and manifest]
    #   引数: [workspace: output folder, source: original, mask: selected area, candidates: image rows, metadata: provenance]
    #   戻り値: [tuple: source hash, candidate paths, manifest path]
    # }
    def save_run(
        self,
        workspace: str | Path,
        source: bytes,
        mask: bytes,
        candidates: tuple,
        metadata: dict[str, Any],
    ) -> tuple[str, tuple[str, ...], str, str]: ...


# {
#   責務: [ExpressionRetouchDataMessenger: forward Process requests to the Data endpoint]
#   フィールド: [data endpoint]
#   処理: [provide a narrow one-way messenger for image and artifact operations]
# }
class ExpressionRetouchDataMessenger:
    # {
    #   責務: [__init__: bind the Data endpoint]
    #   処理: [store the endpoint behind the Process messenger boundary]
    #   引数: [endpoint: Data port implementation]
    #   戻り値: []
    # }
    def __init__(self, endpoint: ExpressionRetouchDataPort) -> None:
        self._endpoint = endpoint

    # {
    #   責務: [normalize: forward image normalization]
    #   処理: [delegate to Data]
    #   引数: [source: encoded image]
    #   戻り値: [bytes: normalized image]
    # }
    def normalize(self, source: bytes) -> bytes:
        return self._endpoint.normalize(source)

    # {
    #   責務: [analyze: forward face detection]
    #   処理: [delegate to Data]
    #   引数: [source: normalized image]
    #   戻り値: [FaceAnalysis: detection result]
    # }
    def analyze(self, source: bytes) -> FaceAnalysis:
        return self._endpoint.analyze(source)

    # {
    #   責務: [mask: forward local mask generation]
    #   処理: [delegate to Data]
    #   引数: [size: dimensions, face: selected face, parts: requested regions, manual: optional override mask]
    #   戻り値: [bytes: grayscale mask]
    # }
    def mask(self, size, face, parts, manual):
        return self._endpoint.mask(size, face, parts, manual)

    # {
    #   責務: [measure: forward candidate-preservation analysis]
    #   処理: [delegate to Data]
    #   引数: [source: original image, candidate: raw output, mask: local area]
    #   戻り値: [tuple: preservation signals]
    # }
    def measure(self, source, candidate, mask):
        return self._endpoint.measure(source, candidate, mask)

    # {
    #   責務: [composite: forward guaranteed local compositing]
    #   処理: [delegate to Data]
    #   引数: [source: original image, candidate: raw output, mask: local area]
    #   戻り値: [bytes: safe output image]
    # }
    def composite(self, source, candidate, mask):
        return self._endpoint.composite(source, candidate, mask)

    # {
    #   責務: [save_run: forward artifact and history persistence]
    #   処理: [delegate to Data]
    #   引数: [workspace: output folder, source: original, mask: selected area, candidates: generated rows, metadata: provenance]
    #   戻り値: [tuple: artifact paths and source hash]
    # }
    def save_run(self, workspace, source, mask, candidates, metadata):
        return self._endpoint.save_run(workspace, source, mask, candidates, metadata)
