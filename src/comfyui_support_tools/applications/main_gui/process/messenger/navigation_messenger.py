"""ProcessNavigationMessenger: delegates navigation requests without interpreting payloads."""

from comfyui_support_tools.applications.main_gui.process.commander.navigation_commander import (
    NavigationCommander,
)
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry


# {
# 責務: [ProcessNavigationMessenger: NavigationCommander operationsを上位UI layerへ転送する]
# フィールド: [_target: NavigationCommander]
# }
class ProcessNavigationMessenger:
    # {
    #   責務: [__init__: NavigationCommander delegateを保持する]
    #   処理: [navigation messagesをtargetへ接続する]
    #   引数: [self: messenger, target: NavigationCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, target: NavigationCommander):
        self._target = target

    # {
    #   責務: [categories: tool categoriesをProcess commanderから取得する]
    #   処理: [target.categories resultを返す]
    #   引数: [self: messenger]
    #   戻り値: [category name tuple]
    # }
    def categories(self) -> tuple[str, ...]:
        return self._target.categories()

    # {
    #   責務: [select_section: section selection requestをcommanderへ転送する]
    #   処理: [target.select_sectionへsectionを渡す]
    #   引数: [self: messenger, section: section key]
    #   戻り値: [ToolEntry tuple: section内tool]
    # }
    def select_section(self, section: str) -> tuple[ToolEntry, ...]:
        return self._target.select_section(section)

    # {
    #   責務: [filter_tools: text/category filtersをcommanderへ転送する]
    #   処理: [target.filter_toolsへquery/categoryを渡す]
    #   引数: [self: messenger, query: search text, category: filter value]
    #   戻り値: [ToolEntry tuple: matching tools]
    # }
    def filter_tools(self, query: str, category: str) -> tuple[ToolEntry, ...]:
        return self._target.filter_tools(query, category)

    # {
    #   責務: [visible_tools: current filtered ToolEntry listを取得する]
    #   処理: [target.visible_toolsへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [ToolEntry tuple]
    # }
    def visible_tools(self) -> tuple[ToolEntry, ...]:
        return self._target.visible_tools()

    # {
    #   責務: [request_open: tool open requestをProcess commanderへ転送する]
    #   処理: [target.request_openへtool IDを渡す]
    #   引数: [self: messenger, tool_id: requested tool identifier]
    #   戻り値: [str: open destination]
    # }
    def request_open(self, tool_id: str) -> str:
        return self._target.request_open(tool_id)
