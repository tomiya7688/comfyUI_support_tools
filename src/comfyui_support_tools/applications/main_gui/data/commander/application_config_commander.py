from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.data.processing.application_config_processing import (
    load_application_config,
)
from comfyui_support_tools.shared.contracts.application_models import ApplicationConfig


# {
# 責務: [ApplicationConfigCommander: application config読み込み関数をData commander境界へ公開する]
# フィールド: [stateless delegate。instance fieldなし]
# }
class ApplicationConfigCommander:
    """Directs config loading without performing persistence work itself."""

    # {
    #   責務: [load: path上のapplication configをprocessing関数へ委譲する]
    #   処理: [load_application_configのresult/errorを変更せず返す]
    #   引数: [self: commander, path: config file path]
    #   戻り値: [ApplicationConfig: 読み込んだname/version]
    #   エラー: [load_application_configのfilesystem/parse errors]
    #   副作用: [config fileを読み込む]
    # }
    def load(self, path: Path) -> ApplicationConfig:
        return load_application_config(path)
