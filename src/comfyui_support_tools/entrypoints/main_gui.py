from __future__ import annotations

from comfyui_support_tools.applications.main_gui.ui.commander.shell_commander import ShellCommander


def create_shell_commander() -> ShellCommander:
    """Build the new Main GUI application boundary without starting legacy UI."""
    return ShellCommander()
