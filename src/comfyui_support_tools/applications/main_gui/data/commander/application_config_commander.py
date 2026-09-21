from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.data.processing.application_config_processing import (
    load_application_config,
)
from comfyui_support_tools.shared.contracts.application_models import ApplicationConfig


class ApplicationConfigCommander:
    """Directs config loading without performing persistence work itself."""

    def load(self, path: Path) -> ApplicationConfig:
        return load_application_config(path)
