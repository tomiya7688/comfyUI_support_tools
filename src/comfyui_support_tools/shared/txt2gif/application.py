"""Backend registry and application orchestration for short-loop GIF jobs."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from .contracts import AnimationFrameBackend, Txt2GifRequest, Txt2GifResult
from .pipeline import create_txt2gif


# {
#   責務: [AnimationBackendRegistry: still/mask backend implementationsをstable IDで管理する]
#   フィールド: [backend_id -> AnimationFrameBackend mapping]
#   処理: [new AnimateDiff, segmentation, and key-art adapters register without changing the pipeline]
# }
class AnimationBackendRegistry:
    # {
    #   責務: [__init__: optional animation backend groupを登録する]
    #   処理: [initialize an empty registry then validate the caller-provided adapters]
    #   引数: [backends: iterable of stable IDs and backend adapters]
    #   戻り値: []
    #   エラー: [ValueError or TypeError: duplicate ID or invalid backend]
    # }
    def __init__(self, backends: Iterable[tuple[str, AnimationFrameBackend]] = ()) -> None:
        self._backends: dict[str, AnimationFrameBackend] = {}
        for backend_id, backend in backends:
            self.register(backend_id, backend)

    # {
    #   責務: [register: one explicit animation providerを追加する]
    #   処理: [normalize ID and reject empty/duplicate backend registrations]
    #   引数: [backend_id: stable provider name, backend: typed frame backend]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: invalid backend registration]
    # }
    def register(self, backend_id: str, backend: AnimationFrameBackend) -> None:
        key = backend_id.strip().casefold()
        if not key:
            raise ValueError("animation backend ID must not be empty")
        if key in self._backends:
            raise ValueError(f"animation backend is already registered: {backend_id}")
        if not callable(getattr(backend, "generate_still", None)) or not callable(
            getattr(backend, "extract_layers", None)
        ):
            raise TypeError(
                "animation backend must implement still generation and layer extraction"
            )
        self._backends[key] = backend

    # {
    #   責務: [get: backend IDでregistered animation adapterを取得する]
    #   処理: [perform case-insensitive explicit lookup without implicit fallback]
    #   引数: [backend_id: stable adapter identifier]
    #   戻り値: [AnimationFrameBackend: matching still/layer backend]
    #   エラー: [LookupError: adapter is not registered]
    # }
    def get(self, backend_id: str) -> AnimationFrameBackend:
        try:
            return self._backends[backend_id.strip().casefold()]
        except KeyError as error:
            raise LookupError(f"animation backend is not registered: {backend_id}") from error

    # {
    #   責務: [backend_ids: registered provider IDsをstable順で返す]
    #   処理: [expose sorted IDs for UI strategy selection]
    #   引数: [self: backend registry]
    #   戻り値: [tuple[str, ...]: available provider IDs]
    # }
    @property
    def backend_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._backends))


# {
#   責務: [Txt2GifApplication: selected backend and requestをshared generation pipelineへ接続する]
#   フィールド: [AnimationBackendRegistry]
#   処理: [route explicit provider, emit progress and return GIF artifact diagnostics]
# }
class Txt2GifApplication:
    # {
    #   責務: [__init__: injected animation providersをapplicationへ設定する]
    #   処理: [retain the shared adapter registry]
    #   引数: [backends: explicit adapter registry]
    #   戻り値: []
    # }
    def __init__(self, backends: AnimationBackendRegistry) -> None:
        self._backends = backends

    # {
    #   責務: [generate: requested loop jobを選択providerで実行する]
    #   処理: [resolve backend ID, run canonical still/key-art/encoding pipeline and pass progress messages]
    #   引数: [request: loop and output constraints, backend_id: selected strategy, progress: optional status callback]
    #   戻り値: [Txt2GifResult: committed GIF and diagnostics]
    #   エラー: [LookupError, ValueError or OSError: routing, generation or encoding failure]
    # }
    def generate(
        self,
        request: Txt2GifRequest,
        backend_id: str,
        *,
        progress: Callable[[str], None] | None = None,
    ) -> Txt2GifResult:
        backend = self._backends.get(backend_id)
        return create_txt2gif(request, backend, progress=progress)
