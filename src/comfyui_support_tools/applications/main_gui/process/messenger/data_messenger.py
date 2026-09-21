from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.data.commander.application_config_commander import (
    ApplicationConfigCommander,
)
from comfyui_support_tools.shared.contracts.application_models import ApplicationConfig


class DataMessenger:
    """Carries Process-layer config requests to the Data layer."""

    def __init__(self, commander: ApplicationConfigCommander | None = None):
        self._commander = commander or ApplicationConfigCommander()

    def load_config(self, path: Path) -> ApplicationConfig:
        return self._commander.load(path)
