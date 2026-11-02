"""UI-side request messenger for Process commands."""

from typing import Any, Protocol


# {
#   責務: [ExpressionRetouchProcessPort: describe the UI-facing Process API]
#   フィールド: [analyze, available_backends, retouch operations]
#   処理: [keep the UI independent from processor implementation modules]
# }
class ExpressionRetouchProcessPort(Protocol):
    # {
    #   責務: [analyze: find targetable face regions]
    #   処理: [return stable detections and warning strings]
    #   引数: [source_image: encoded image]
    #   戻り値: [FaceAnalysis: detection result]
    # }
    def analyze(self, source_image: bytes): ...

    # {
    #   責務: [preview_mask: provide a detector-region mask preview]
    #   処理: [return automatic selected-region geometry]
    #   引数: [analysis: face results, face_index: selected face, parts: selected areas]
    #   戻り値: [bytes: PNG mask]
    # }
    def preview_mask(self, analysis, face_index: int, parts: tuple) -> bytes: ...

    # {
    #   責務: [retouch: execute a localized edit]
    #   処理: [generate, score, composite and save candidate outputs]
    #   引数: [request: edit request, workspace: output directory, backend_id: optional model route]
    #   戻り値: [ExpressionRetouchResult: persisted result]
    # }
    def retouch(self, request, workspace, backend_id=None): ...

    # {
    #   責務: [available_backends: list configured backend IDs]
    #   処理: [return backend catalog]
    #   引数: [self: Process endpoint]
    #   戻り値: [tuple[str, ...]: backend IDs]
    # }
    @property
    def available_backends(self) -> tuple[str, ...]: ...


# {
#   責務: [ExpressionRetouchProcessMessenger: pass named UI requests to Process]
#   フィールド: [Process application endpoint]
#   処理: [dispatch stable operation IDs and keep transport replaceable]
# }
class ExpressionRetouchProcessMessenger:
    # {
    #   責務: [__init__: bind Process endpoint]
    #   処理: [store the UI-to-Process communication interface]
    #   引数: [endpoint: Process API implementation]
    #   戻り値: []
    # }
    def __init__(self, endpoint: ExpressionRetouchProcessPort) -> None:
        self._endpoint = endpoint

    # {
    #   責務: [send: route one named UI request]
    #   処理: [lookup an allowed operation and forward its arguments]
    #   引数: [operation: operation name, args: positional arguments, values: keyword arguments]
    #   戻り値: [Any: Process result]
    # }
    def send(self, operation: str, *args: object, **values: object) -> Any:
        allowed = {
            "analyze": self._endpoint.analyze,
            "preview_mask": self._endpoint.preview_mask,
            "retouch": self._endpoint.retouch,
        }
        if operation == "available_backends":
            return self._endpoint.available_backends
        if operation not in allowed:
            raise ValueError(f"unsupported Expression Retouch operation: {operation}")
        return allowed[operation](*args, **values)
