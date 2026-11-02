"""Route Manga Creator editor requests through the UI messenger."""

from typing import Any

from comfyui_support_tools.applications.manga_creator.ui.messenger.process_messenger import (
    MangaProcessMessenger,
)


# {
# 責務: [MangaCreatorUiCommander: pass user actions to Process communication]
# フィールド: [Process messenger]
# 処理: [keep Tk event handlers independent from Process implementation modules]
# }
class MangaCreatorUiCommander:
    # {
    # 責務: [__init__: bind the UI-to-Process messenger]
    # 処理: [store the in-process communication endpoint]
    # 引数: [self: UI Commander, messenger: process messenger]
    # 戻り値: [None: commander initialized]
    # }
    def __init__(self, messenger: MangaProcessMessenger) -> None:
        self._messenger = messenger

    # {
    # 責務: [send: route one UI action to Process]
    # 処理: [forward the named operation and payload]
    # 引数: [operation: application action, args: positional payload, values: named payload]
    # 戻り値: [Any: Process response]
    # }
    def send(self, operation: str, *args: Any, **values: Any) -> Any:
        return self._messenger.send(operation, *args, **values)
