from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.process.messenger.data_messenger import DataMessenger
from comfyui_support_tools.applications.main_gui.process.processing.bootstrap_processing import (
    build_application_status,
)
from comfyui_support_tools.shared.contracts.application_models import ApplicationStatus


class BootstrapCommander:
    """Directs the bootstrap flow across Process and Data boundaries."""

    def __init__(self, data_messenger: DataMessenger | None = None):
        self._data_messenger = data_messenger or DataMessenger()

    def bootstrap(self, config_path: Path) -> ApplicationStatus:
        config = self._data_messenger.load_config(config_path)
        return build_application_status(config)
