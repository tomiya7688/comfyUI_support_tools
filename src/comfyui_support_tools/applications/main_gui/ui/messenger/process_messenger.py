from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.process.commander.bootstrap_commander import (
    BootstrapCommander,
)
from comfyui_support_tools.shared.contracts.application_models import ApplicationStatus


class ProcessMessenger:
    """Carries UI-layer bootstrap requests to the Process layer."""

    def __init__(self, commander: BootstrapCommander | None = None):
        self._commander = commander or BootstrapCommander()

    def bootstrap(self, config_path: Path) -> ApplicationStatus:
        return self._commander.bootstrap(config_path)
