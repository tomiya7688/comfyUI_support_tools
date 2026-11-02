from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.process.messenger.data_messenger import (
    DataMessenger,
)
from comfyui_support_tools.applications.main_gui.process.processing.bootstrap_processing import (
    build_application_status,
)
from comfyui_support_tools.shared.contracts.application_models import ApplicationStatus


# {
# 責務: [BootstrapCommander: config読み込みとapplication status組み立てのProcess flowを調整する]
# フィールド: [_data_messenger: config read boundary]
# }
class BootstrapCommander:
    """Directs the bootstrap flow across Process and Data boundaries."""

    # {
    #   責務: [__init__: optional data messengerまたはdefault messengerを保持する]
    #   処理: [NoneのときDataMessengerを作りbootstrap依存を組み立てる]
    #   引数: [self: commander, data_messenger: optional config data boundary]
    #   戻り値: [なし]
    # }
    def __init__(self, data_messenger: DataMessenger | None = None):
        self._data_messenger = data_messenger or DataMessenger()

    # {
    #   責務: [bootstrap: configを読み込みApplicationStatus contractへ変換する]
    #   処理: [DataMessenger.load_configを呼び、build_application_statusへ渡す]
    #   引数: [self: commander, config_path: application config path]
    #   戻り値: [ApplicationStatus: name/version/ready state]
    #   エラー: [data read/JSON parse error]
    # }
    def bootstrap(self, config_path: Path) -> ApplicationStatus:
        config = self._data_messenger.load_config(config_path)
        return build_application_status(config)
