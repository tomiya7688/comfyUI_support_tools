"""Data-side endpoint for image decoding, face analysis, masks, and persistence."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from comfyui_support_tools.applications.expression_retouch.data.processing.face_analysis import (
    analyze_faces,
    normalize_source_image,
)
from comfyui_support_tools.applications.expression_retouch.data.processing.face_mask import (
    composite_local_edit,
    create_edit_mask,
    measure_candidate_preservation,
)
from comfyui_support_tools.applications.expression_retouch.data.processing.retouch_store import (
    ExpressionRetouchStore,
)
from comfyui_support_tools.shared.contracts.expression_retouch import (
    DetectedFace,
    FaceAnalysis,
    FacePart,
)


# {
#   責務: [ExpressionRetouchDataEndpoint: expose image IO and retouch persistence to Process]
#   フィールド: [immutable artifact store]
#   処理: [route source normalization, face detection, mask generation, local composition, and run storage]
# }
class ExpressionRetouchDataEndpoint:
    # {
    #   責務: [__init__: configure the data-backed retouch endpoint]
    #   処理: [bind immutable run storage]
    #   引数: [store: optional testable artifact store]
    #   戻り値: []
    # }
    def __init__(
        self,
        store: ExpressionRetouchStore | None = None,
        analyzer: Callable[[bytes], FaceAnalysis] = analyze_faces,
    ) -> None:
        self._store = store or ExpressionRetouchStore()
        self._analyzer = analyzer

    # {
    #   責務: [normalize: normalize and bound a source image]
    #   処理: [apply orientation and encode canonical PNG bytes]
    #   引数: [source: encoded input image]
    #   戻り値: [bytes: normalized PNG]
    # }
    def normalize(self, source: bytes) -> bytes:
        return normalize_source_image(source)

    # {
    #   責務: [analyze: detect faces in an image]
    #   処理: [run the configured OpenCV face detector]
    #   引数: [source: canonical image bytes]
    #   戻り値: [FaceAnalysis: detections and limitations]
    # }
    def analyze(self, source: bytes) -> FaceAnalysis:
        return self._analyzer(source)

    # {
    #   責務: [mask: create a local mask for selected face regions]
    #   処理: [use detected part estimates or a user-refined mask]
    #   引数: [size: source canvas, face: selected face, parts: requested parts, manual: optional replacement mask]
    #   戻り値: [bytes: feathered grayscale mask]
    # }
    def mask(
        self,
        size: tuple[int, int],
        face: DetectedFace,
        parts: tuple[FacePart, ...],
        manual: bytes | None,
    ) -> bytes:
        return create_edit_mask(size, face, parts, manual)

    # {
    #   責務: [measure: quantify raw candidate locality and outside-mask preservation]
    #   処理: [compare source and candidate pixels against the selected mask]
    #   引数: [source: original PNG, candidate: raw backend output, mask: allowed edit area]
    #   戻り値: [tuple[float, float, tuple[str, ...]]: identity proxy, locality, limitations]
    # }
    def measure(self, source: bytes, candidate: bytes, mask: bytes):
        return measure_candidate_preservation(source, candidate, mask)

    # {
    #   責務: [composite: enforce source-pixel preservation outside mask]
    #   処理: [blend candidate and original using the feathered mask]
    #   引数: [source: original PNG, candidate: backend image, mask: local edit area]
    #   戻り値: [bytes: composited PNG]
    # }
    def composite(self, source: bytes, candidate: bytes, mask: bytes) -> bytes:
        return composite_local_edit(source, candidate, mask)

    # {
    #   責務: [save_run: persist source, mask, candidates and history]
    #   処理: [write immutable images and one atomic JSON history manifest]
    #   引数: [workspace: output directory, source: canonical source, mask: selected edit region, candidates: candidate images/metadata, metadata: request provenance]
    #   戻り値: [tuple[str, tuple[str, ...], str, str]: source hash, candidate paths, mask path, manifest path]
    # }
    def save_run(
        self,
        workspace: str | Path,
        source: bytes,
        mask: bytes,
        candidates: tuple[tuple[bytes, dict[str, Any]], ...],
        metadata: dict[str, Any],
    ) -> tuple[str, tuple[str, ...], str, str]:
        return self._store.save_run(workspace, source, mask, candidates, metadata)
