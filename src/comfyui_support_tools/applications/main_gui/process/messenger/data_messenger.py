from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.data.commander.application_config_commander import (
    ApplicationConfigCommander,
)
from comfyui_support_tools.shared.contracts.application_models import ApplicationConfig


# {
# 責務: [DataMessenger: ProcessからApplicationConfig Data commanderへload requestを届ける]
# フィールド: [_commander: ApplicationConfigCommander]
# }
class DataMessenger:
    """Carries Process-layer config requests to the Data layer."""

    # {
    #   責務: [__init__: supplied commanderまたはdefault ApplicationConfigCommanderを保持する]
    #   処理: [Noneならdefault config loader boundaryを構築する]
    #   引数: [self: messenger, commander: optional ApplicationConfigCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, commander: ApplicationConfigCommander | None = None):
        self._commander = commander or ApplicationConfigCommander()

    # {
    #   責務: [load_config: config pathをData commanderへ渡してApplicationConfigを取得する]
    #   処理: [commander.loadのresult/errorを変換せず返す]
    #   引数: [self: messenger, path: config JSON path]
    #   戻り値: [ApplicationConfig]
    #   エラー: [commander/load functionのfilesystem/JSON error]
    # }
    def load_config(self, path: Path) -> ApplicationConfig:
        return self._commander.load(path)
