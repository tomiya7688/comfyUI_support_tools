"""UiNavigationMessenger: delegates navigation requests without interpreting payloads."""

from comfyui_support_tools.applications.main_gui.process.messenger.navigation_messenger import (
    ProcessNavigationMessenger,
)
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry


# {
# 責務: [UiNavigationMessenger: UI navigation APIをProcessNavigationMessengerへ接続する]
# フィールド: [_target: ProcessNavigationMessenger]
# }
class UiNavigationMessenger:
    # {
    #   責務: [__init__: ProcessNavigationMessenger delegateを保持する]
    #   処理: [navigation UI messagesのtargetを設定する]
    #   引数: [self: messenger, target: ProcessNavigationMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: ProcessNavigationMessenger):
        self._target = target

    # {
    #   責務: [categories: UI向けtool category listを取得する]
    #   処理: [target.categoriesへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [category string tuple]
    # }
    def categories(self) -> tuple[str, ...]:
        return self._target.categories()

    # {
    #   責務: [select_section: Library section updateをProcessへ送る]
    #   処理: [target.select_sectionへsectionを渡す]
    #   引数: [self: messenger, section: section key]
    #   戻り値: [section ToolEntry tuple]
    # }
    def select_section(self, section: str) -> tuple[ToolEntry, ...]:
        return self._target.select_section(section)

    # {
    #   責務: [filter_tools: query/category filter updateをProcessへ送る]
    #   処理: [target.filter_toolsへinput valuesを渡す]
    #   引数: [self: messenger, query: search text, category: category filter]
    #   戻り値: [filtered ToolEntry tuple]
    # }
    def filter_tools(self, query: str, category: str) -> tuple[ToolEntry, ...]:
        return self._target.filter_tools(query, category)

    # {
    #   責務: [visible_tools: current visible tool listをProcessから取得する]
    #   処理: [target.visible_toolsを呼ぶ]
    #   引数: [self: messenger]
    #   戻り値: [ToolEntry tuple]
    # }
    def visible_tools(self) -> tuple[ToolEntry, ...]:
        return self._target.visible_tools()

    # {
    #   責務: [request_open: selected tool IDをlegacy open requestとしてProcessへ送る]
    #   処理: [target.request_openにtool_idを渡す]
    #   引数: [self: messenger, tool_id: selected ToolEntry ID]
    #   戻り値: [str: open destination]
    # }
    def request_open(self, tool_id: str) -> str:
        return self._target.request_open(tool_id)
