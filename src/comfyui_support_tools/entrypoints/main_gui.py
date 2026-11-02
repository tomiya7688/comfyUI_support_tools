from __future__ import annotations

from comfyui_support_tools.applications.main_gui.ui.commander.shell_commander import ShellCommander


# {
#   責務: [create_shell_commander: legacy UIを起動せず新Main GUI application boundaryを構築する]
#   処理: [ShellCommanderを生成する]
#   引数: []
#   戻り値: [ShellCommander: Main GUI shell操作用commander]
# }
def create_shell_commander() -> ShellCommander:
    """Build the new Main GUI application boundary without starting legacy UI."""
    return ShellCommander()
