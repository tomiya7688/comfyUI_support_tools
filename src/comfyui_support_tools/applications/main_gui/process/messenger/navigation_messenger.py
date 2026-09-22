"""ProcessNavigationMessenger: delegates navigation requests without interpreting payloads."""
from comfyui_support_tools.applications.main_gui.process.commander.navigation_commander import NavigationCommander
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry


class ProcessNavigationMessenger:
    def __init__(self, target: NavigationCommander):
        self._target = target

    def categories(self) -> tuple[str, ...]:
        return self._target.categories()

    def select_section(self, section: str) -> tuple[ToolEntry, ...]:
        return self._target.select_section(section)

    def filter_tools(self, query: str, category: str) -> tuple[ToolEntry, ...]:
        return self._target.filter_tools(query, category)

    def visible_tools(self) -> tuple[ToolEntry, ...]:
        return self._target.visible_tools()

    def request_open(self, tool_id: str) -> str:
        return self._target.request_open(tool_id)
