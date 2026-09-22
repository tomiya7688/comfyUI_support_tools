"""Session navigation state; no widgets, persistence, or backend imports."""
from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry

SECTIONS = ("all", "images", "videos", "dataset", "generated", "favorites", "recent")


class NavigationProcessing:
    def __init__(self, tools: tuple[ToolEntry, ...]):
        if len({tool.id for tool in tools}) != len(tools):
            raise ValueError("Tool IDs must be unique")
        self.tools = tools
        self.section = "all"
        self.query = ""
        self.category = ""
        self.recent: list[str] = []

    def categories(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(tool.category for tool in self.tools))

    def select_section(self, section: str) -> tuple[ToolEntry, ...]:
        if section not in SECTIONS:
            raise ValueError(f"Unknown Library section: {section}")
        self.section = section
        return self.visible_tools()

    def filter_tools(self, query: str, category: str) -> tuple[ToolEntry, ...]:
        if category and category not in self.categories():
            raise ValueError(f"Unknown tool category: {category}")
        self.query = query.strip().casefold()
        self.category = category
        return self.visible_tools()

    def visible_tools(self) -> tuple[ToolEntry, ...]:
        tools = self.tools
        if self.section == "recent":
            by_id = {tool.id: tool for tool in tools}
            tools = tuple(by_id[key] for key in self.recent if key in by_id)
        return tuple(
            tool for tool in tools
            if (not self.category or tool.category == self.category)
            and (not self.query or self.query in
                 f"{tool.id} {tool.label} {tool.category}".casefold())
        )

    def request_open(self, tool_id: str) -> str:
        if tool_id not in {tool.id for tool in self.tools}:
            raise ValueError(f"Unknown tool: {tool_id}")
        self.recent = [tool_id, *(key for key in self.recent if key != tool_id)][:12]
        return tool_id
