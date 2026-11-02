"""Transport editor commands to the Process application boundary."""

from typing import Any


# {
# 責務: [MangaProcessMessenger: forward UI command requests across the application boundary]
# フィールド: [injected Process application target]
# 処理: [transport a command name, positional values and named values without manga logic]
# }
class MangaProcessMessenger:
    # {
    # 責務: [__init__: bind an application Process endpoint]
    # 処理: [retain the injected request target]
    # 引数: [self: UI messenger, target: Process application]
    # 戻り値: [None: endpoint bound]
    # }
    def __init__(self, target: object) -> None:
        self._target = target

    # {
    # 責務: [send: forward one named application request]
    # 処理: [invoke the matching Process endpoint operation and return its result]
    # 引数: [operation: endpoint operation name, args: positional payload, values: named payload]
    # 戻り値: [Any: Process application response]
    # }
    def send(self, operation: str, *args: Any, **values: Any) -> Any:
        endpoint = getattr(self._target, operation, None)
        if endpoint is None or operation.startswith("_") or not callable(endpoint):
            raise ValueError(f"unknown Manga Creator operation: {operation}")
        return endpoint(*args, **values)
