from __future__ import annotations

from pathlib import Path

from comfyui_support_tools.applications.main_gui.ui.messenger.process_messenger import ProcessMessenger
from comfyui_support_tools.applications.main_gui.ui.processing.status_text_processing import format_status_text


class ShellCommander:
    """Directs initial shell state loading and UI formatting."""

    def __init__(self, process_messenger: ProcessMessenger | None = None):
        self._process_messenger = process_messenger or ProcessMessenger()

    def initialize(self, config_path: Path) -> str:
        status = self._process_messenger.bootstrap(config_path)
        return format_status_text(status)
