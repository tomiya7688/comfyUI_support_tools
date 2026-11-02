"""Named panel generation backend catalog for per-panel routing."""

from __future__ import annotations

import re

from comfyui_support_tools.shared.contracts.manga_creator import PanelGenerationBackend

_BACKEND_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


# {
# 責務: [PanelBackendRegistry: register and resolve named panel generators]
# フィールド: [backend ID to adapter map]
# 処理: [route each panel to an injected model or storyboard backend]
# }
class PanelBackendRegistry:
    # {
    # 責務: [__init__: create an empty backend catalog]
    # 処理: [initialize the named adapter map]
    # 引数: [self: registry]
    # 戻り値: [None: catalog initialized]
    # }
    def __init__(self) -> None:
        self._backends: dict[str, PanelGenerationBackend] = {}

    # {
    # 責務: [register: add a replaceable panel generation backend]
    # 処理: [validate the ID and prevent duplicate adapter registration]
    # 引数: [name: backend ID, backend: image generation adapter]
    # 戻り値: [None: adapter registered]
    # }
    def register(self, name: str, backend: PanelGenerationBackend) -> None:
        if not _BACKEND_NAME.fullmatch(name):
            raise ValueError("backend name must be a portable 1-64 character ID")
        if name in self._backends:
            raise ValueError(f"panel backend is already registered: {name}")
        self._backends[name] = backend

    # {
    # 責務: [resolve: choose one registered panel adapter]
    # 処理: [raise a clear error when the selected model is unavailable]
    # 引数: [name: requested backend ID]
    # 戻り値: [PanelGenerationBackend: selected adapter]
    # }
    def resolve(self, name: str) -> PanelGenerationBackend:
        try:
            return self._backends[name]
        except KeyError as error:
            raise KeyError(f"panel backend is not registered: {name}") from error

    # {
    # 責務: [names: list configured backend IDs]
    # 処理: [return stable sorted identifiers]
    # 引数: [self: registry]
    # 戻り値: [tuple[str, ...]: available backends]
    # }
    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._backends))
