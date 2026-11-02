"""Display metadata for a tool, never a reference to its implementation."""

from dataclasses import dataclass


# {
# 責務: [ToolEntry: 実装参照を含まず、tool一覧表示に必要なmetadataを保持する]
# フィールド: [id: tool識別子, label: 表示名, category: 分類名]
# }
@dataclass(frozen=True)
class ToolEntry:
    id: str
    label: str
    category: str
