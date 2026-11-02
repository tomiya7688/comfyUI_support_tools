"""Session navigation state; no widgets, persistence, or backend imports."""

from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry

SECTIONS = ("all", "images", "videos", "dataset", "generated", "favorites", "recent")


# {
# 責務: [NavigationProcessing: widgetsから独立したtool section/filter/recent navigation stateを管理する]
# フィールド: [tools, section, query, category, recent tool IDs]
# }
class NavigationProcessing:
    # {
    #   責務: [__init__: ToolEntry registryとdefault all-section stateを初期化する]
    #   処理: [unique IDを検証しtool tupleとempty filters/recent stateを保持する]
    #   引数: [self: navigation state, tools: ToolEntry registry]
    #   戻り値: [なし]
    #   エラー: [ValueError: tool IDが重複]
    # }
    def __init__(self, tools: tuple[ToolEntry, ...]):
        if len({tool.id for tool in tools}) != len(tools):
            raise ValueError("Tool IDs must be unique")
        self.tools = tools
        self.section = "all"
        self.query = ""
        self.category = ""
        self.recent: list[str] = []

    # {
    #   責務: [categories: registry内に現れるcategory名を初出順で返す]
    #   処理: [dict insertion orderを使って重複categoryを除く]
    #   引数: [self: navigation state]
    #   戻り値: [tuple[str,...]: unique category labels]
    # }
    def categories(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(tool.category for tool in self.tools))

    # {
    #   責務: [select_section: supported Library sectionを選択しmatching toolsを返す]
    #   処理: [section keyを検証しstate更新後visible_toolsへ委譲する]
    #   引数: [self: state, section: all/images/videos/dataset/generated/favorites/recent]
    #   戻り値: [ToolEntry tuple]
    #   エラー: [ValueError: section key不明]
    # }
    def select_section(self, section: str) -> tuple[ToolEntry, ...]:
        if section not in SECTIONS:
            raise ValueError(f"Unknown Library section: {section}")
        self.section = section
        return self.visible_tools()

    # {
    #   責務: [filter_tools: query/category filterを設定しvisible registry subsetを返す]
    #   処理: [categoryをregistryで検証しqueryをtrim/casefoldしてからfilterする]
    #   引数: [self: state, query: search text, category: optional category label]
    #   戻り値: [ToolEntry tuple]
    #   エラー: [ValueError: categoryがregistryに存在しない]
    # }
    def filter_tools(self, query: str, category: str) -> tuple[ToolEntry, ...]:
        if category and category not in self.categories():
            raise ValueError(f"Unknown tool category: {category}")
        self.query = query.strip().casefold()
        self.category = category
        return self.visible_tools()

    # {
    #   責務: [visible_tools: current section/recent/category/queryに一致するToolEntryを返す]
    #   処理: [recent sectionをhistory orderでlookupし、category/query predicateを適用する]
    #   引数: [self: state]
    #   戻り値: [ToolEntry tuple]
    # }
    def visible_tools(self) -> tuple[ToolEntry, ...]:
        tools = self.tools
        if self.section == "recent":
            by_id = {tool.id: tool for tool in tools}
            tools = tuple(by_id[key] for key in self.recent if key in by_id)
        return tuple(
            tool
            for tool in tools
            if (not self.category or tool.category == self.category)
            and (
                not self.query or self.query in f"{tool.id} {tool.label} {tool.category}".casefold()
            )
        )

    # {
    #   責務: [request_open: known tool IDを検証してrecent history先頭へ移す]
    #   処理: [ID不明を拒否し、重複除去後historyを12 entryに制限する]
    #   引数: [self: state, tool_id: requested ToolEntry ID]
    #   戻り値: [str: accepted tool ID]
    #   エラー: [ValueError: registryに存在しないtool]
    # }
    def request_open(self, tool_id: str) -> str:
        if tool_id not in {tool.id for tool in self.tools}:
            raise ValueError(f"Unknown tool: {tool_id}")
        self.recent = [tool_id, *(key for key in self.recent if key != tool_id)][:12]
        return tool_id
