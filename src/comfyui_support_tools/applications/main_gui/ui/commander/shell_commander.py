from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.ui.messenger.process_messenger import (
    ProcessMessenger,
)
from comfyui_support_tools.applications.main_gui.ui.processing.status_text_processing import (
    format_status_text,
)


# {
# 責務: [ShellCommander: bootstrap statusを読み込みUI向けstatus textへ変換する]
# フィールド: [_process_messenger: Process bootstrap boundary]
# }
class ShellCommander:
    """Directs initial shell state loading and UI formatting."""

    # {
    #   責務: [__init__: optional ProcessMessengerまたはdefault bootstrap chainを保持する]
    #   処理: [NoneならProcessMessengerを作る]
    #   引数: [self: commander, process_messenger: optional bootstrap messenger]
    #   戻り値: [なし]
    # }
    def __init__(self, process_messenger: ProcessMessenger | None = None):
        self._process_messenger = process_messenger or ProcessMessenger()

    # {
    #   責務: [initialize: configからbootstrap statusを読みUI表示用textを作る]
    #   処理: [process bootstrapへpathを渡しApplicationStatusをformat_status_textへ変換する]
    #   引数: [self: commander, config_path: configuration JSON path]
    #   戻り値: [str: shell status text]
    #   エラー: [Process/Data config readまたはJSON error]
    #   副作用: [config JSONを読み取る]
    # }
    def initialize(self, config_path: Path) -> str:
        status = self._process_messenger.bootstrap(config_path)
        return format_status_text(status)
