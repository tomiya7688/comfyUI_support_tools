"""Legacy navigation metadata derived from the single tool registry."""

from .tool_registry import TOOL_REGISTRY

TAB_CATALOG = tuple(
    (
        item.legacy_class or item.id,
        item.label.replace("{backend}", "Backend"),
        item.category,
    )
    for item in TOOL_REGISTRY.descriptors
)


# {
#   責務: [tab_index: stable tool IDまたはlegacy class adapterからlegacy orderを返す]
#   処理: [1: central descriptor orderを走査する 2: unknown keyを明示的に拒否する]
#   引数: [tool_id: stable tool ID or legacy class name]
#   戻り値: [legacy shell index]
# }
def tab_index(tool_id: str) -> int:
    for index, item in enumerate(TOOL_REGISTRY.descriptors):
        if tool_id in {item.id, item.legacy_class}:
            return index
    raise ValueError(f"Unknown legacy tool: {tool_id}")
