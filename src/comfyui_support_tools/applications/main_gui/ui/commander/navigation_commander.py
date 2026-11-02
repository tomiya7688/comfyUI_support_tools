"""NavigationUiCommander: delegates navigation requests without interpreting payloads."""

from comfyui_support_tools.applications.main_gui.ui.messenger.navigation_messenger import (
    UiNavigationMessenger,
)
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry


# {
# 責務: [NavigationUiCommander: UI向けLibrary section/filter/tool open APIをUiNavigationMessengerへ接続する]
# フィールド: [_target: UiNavigationMessenger]
# }
class NavigationUiCommander:
    # {
    #   責務: [__init__: UiNavigationMessenger delegateを保持する]
    #   処理: [navigation UI commandsをmessengerへ委譲する]
    #   引数: [self: commander, target: UiNavigationMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: UiNavigationMessenger):
        self._target = target

    # {
    #   責務: [categories: UI picker用unique tool category labelsを取得する]
    #   処理: [target.categoriesへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [tuple[str,...]]
    # }
    def categories(self) -> tuple[str, ...]:
        return self._target.categories()

    # {
    #   責務: [select_section: UI Library sectionを切替えて該当ToolEntryを返す]
    #   処理: [target.select_sectionへsectionを渡す]
    #   引数: [self: commander, section: section key]
    #   戻り値: [ToolEntry tuple]
    # }
    def select_section(self, section: str) -> tuple[ToolEntry, ...]:
        return self._target.select_section(section)

    # {
    #   責務: [filter_tools: UI query/category filterをtool registryへ適用する]
    #   処理: [target.filter_toolsへfilter valuesを渡す]
    #   引数: [self: commander, query: text, category: category label]
    #   戻り値: [matching ToolEntry tuple]
    # }
    def filter_tools(self, query: str, category: str) -> tuple[ToolEntry, ...]:
        return self._target.filter_tools(query, category)

    # {
    #   責務: [visible_tools: current UI filtersのmatching toolsを取得する]
    #   処理: [target.visible_toolsを返す]
    #   引数: [self: commander]
    #   戻り値: [ToolEntry tuple]
    # }
    def visible_tools(self) -> tuple[ToolEntry, ...]:
        return self._target.visible_tools()

    # {
    #   責務: [request_open: UIが選んだtool IDをopen destinationへ解決する]
    #   処理: [target.request_openへIDを渡す]
    #   引数: [self: commander, tool_id: selected ID]
    #   戻り値: [str: requested tool destination]
    # }
    def request_open(self, tool_id: str) -> str:
        return self._target.request_open(tool_id)
