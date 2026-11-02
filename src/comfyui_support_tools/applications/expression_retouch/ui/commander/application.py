"""UI-level command boundary for Expression Retouch."""

from typing import Any

from comfyui_support_tools.applications.expression_retouch.ui.messenger.process_messenger import (
    ExpressionRetouchProcessMessenger,
)


# {
#   責務: [ExpressionRetouchUiCommander: expose user actions through the Process messenger]
#   フィールド: [Process messenger]
#   処理: [pass UI operations without direct access to Data or Process internals]
# }
class ExpressionRetouchUiCommander:
    # {
    #   責務: [__init__: bind the UI messenger]
    #   処理: [store the communication endpoint]
    #   引数: [messenger: UI-to-Process messenger]
    #   戻り値: []
    # }
    def __init__(self, messenger: ExpressionRetouchProcessMessenger) -> None:
        self._messenger = messenger

    # {
    #   責務: [send: route one user action]
    #   処理: [forward operation name, positional values and keyword values]
    #   引数: [operation: command name, args: positional payload, values: named payload]
    #   戻り値: [Any: operation response]
    # }
    def send(self, operation: str, *args: object, **values: object) -> Any:
        return self._messenger.send(operation, *args, **values)
