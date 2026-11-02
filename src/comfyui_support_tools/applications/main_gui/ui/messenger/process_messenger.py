from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.process.commander.bootstrap_commander import (
    BootstrapCommander,
)
from comfyui_support_tools.shared.contracts.application_models import ApplicationStatus


# {
# 責務: [ProcessMessenger: UI bootstrap requestをBootstrapCommanderへ届ける]
# フィールド: [_commander: Process BootstrapCommander]
# }
class ProcessMessenger:
    """Carries UI-layer bootstrap requests to the Process layer."""

    # {
    #   責務: [__init__: supplied/default BootstrapCommanderを保持する]
    #   処理: [Noneならdefault Process bootstrap chainを作る]
    #   引数: [self: messenger, commander: optional BootstrapCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, commander: BootstrapCommander | None = None):
        self._commander = commander or BootstrapCommander()

    # {
    #   責務: [bootstrap: config pathをProcess layerへ送りApplicationStatusを取得する]
    #   処理: [commander.bootstrapへpathを渡す]
    #   引数: [self: messenger, config_path: configuration file]
    #   戻り値: [ApplicationStatus]
    #   エラー: [lower config read/parse errors]
    # }
    def bootstrap(self, config_path: Path) -> ApplicationStatus:
        return self._commander.bootstrap(config_path)
