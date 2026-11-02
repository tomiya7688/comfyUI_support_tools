"""Process-level command boundary for Expression Retouch."""

from pathlib import Path

from comfyui_support_tools.applications.expression_retouch.process.processing.processor import (
    ExpressionRetouchProcessor,
)
from comfyui_support_tools.shared.contracts.expression_retouch import (
    ExpressionEditRequest,
    ExpressionRetouchResult,
    FaceAnalysis,
)


# {
#   責務: [ExpressionRetouchApplication: expose face analysis and local edit workflows]
#   フィールド: [ExpressionRetouchProcessor]
#   処理: [route image analysis, backend registration, edit, and candidate history operations]
# }
class ExpressionRetouchApplication:
    # {
    #   責務: [__init__: bind the expression processing coordinator]
    #   処理: [store the processor behind the Process Commander boundary]
    #   引数: [processor: capability router and edit pipeline]
    #   戻り値: []
    # }
    def __init__(self, processor: ExpressionRetouchProcessor) -> None:
        self._processor = processor

    # {
    #   責務: [available_backends: expose configured editor names]
    #   処理: [delegate deterministic registry listing]
    #   引数: [self: application]
    #   戻り値: [tuple[str, ...]: backend IDs]
    # }
    @property
    def available_backends(self) -> tuple[str, ...]:
        return self._processor.available_backends

    # {
    #   責務: [analyze: return detected faces and confidence limitations]
    #   処理: [delegate source image analysis]
    #   引数: [source_image: encoded source image]
    #   戻り値: [FaceAnalysis: detections]
    # }
    def analyze(self, source_image: bytes) -> FaceAnalysis:
        return self._processor.analyze(source_image)

    # {
    #   責務: [preview_mask: return an automatic edit-mask preview]
    #   処理: [delegate face and region selection to Process]
    #   引数: [analysis: face detections, face_index: target face, parts: selected facial regions]
    #   戻り値: [bytes: grayscale mask]
    # }
    def preview_mask(self, analysis, face_index: int, parts: tuple) -> bytes:
        return self._processor.preview_mask(analysis, face_index, parts)

    # {
    #   責務: [retouch: generate and persist a localized expression edit]
    #   処理: [delegate candidate generation, ranking and artifact storage]
    #   引数: [request: structured edit intent, workspace: output folder, backend_id: optional backend choice]
    #   戻り値: [ExpressionRetouchResult: candidate history]
    # }
    def retouch(
        self,
        request: ExpressionEditRequest,
        workspace: str | Path,
        backend_id: str | None = None,
    ) -> ExpressionRetouchResult:
        return self._processor.retouch(request, workspace, backend_id)
