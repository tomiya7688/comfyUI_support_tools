"""NavigationCommander: delegates navigation requests without interpreting payloads."""

from comfyui_support_tools.applications.main_gui.process.processing.navigation_processing import (
    NavigationProcessing,
)
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry


# {
# 責務: [NavigationCommander: NavigationProcessingへのsection/filter/open操作を転送する]
# フィールド: [_target: navigation state/processing component]
# }
class NavigationCommander:
    # {
    #   責務: [__init__: NavigationProcessing delegateを保持する]
    #   処理: [targetをnavigation operationsの委譲先に設定する]
    #   引数: [self: commander, target: NavigationProcessing]
    #   戻り値: [なし]
    # }
    def __init__(self, target: NavigationProcessing):
        self._target = target

    # {
    #   責務: [categories: tool registryにあるcategory labelsを取得する]
    #   処理: [target.categories resultをそのまま返す]
    #   引数: [self: commander]
    #   戻り値: [category name tuple]
    # }
    def categories(self) -> tuple[str, ...]:
        return self._target.categories()

    # {
    #   責務: [select_section: 指定sectionのtool listへ切り替える]
    #   処理: [target.select_sectionへsectionを渡す]
    #   引数: [self: commander, section: all/section key]
    #   戻り値: [sectionで表示するToolEntry tuple]
    # }
    def select_section(self, section: str) -> tuple[ToolEntry, ...]:
        return self._target.select_section(section)

    # {
    #   責務: [filter_tools: query/category条件をnavigation filterへ適用する]
    #   処理: [target.filter_toolsへ引数を渡す]
    #   引数: [self: commander, query: text query, category: category filter]
    #   戻り値: [filtered ToolEntry tuple]
    # }
    def filter_tools(self, query: str, category: str) -> tuple[ToolEntry, ...]:
        return self._target.filter_tools(query, category)

    # {
    #   責務: [visible_tools: current section/filterに一致するtool一覧を取得する]
    #   処理: [target.visible_toolsへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [visible ToolEntry tuple]
    # }
    def visible_tools(self) -> tuple[ToolEntry, ...]:
        return self._target.visible_tools()

    # {
    #   責務: [request_open: tool IDのopen requestをlegacy destination stringへ解決する]
    #   処理: [target.request_openへIDを渡す]
    #   引数: [self: commander, tool_id: selected tool ID]
    #   戻り値: [str: requested destination]
    # }
    def request_open(self, tool_id: str) -> str:
        return self._target.request_open(tool_id)
