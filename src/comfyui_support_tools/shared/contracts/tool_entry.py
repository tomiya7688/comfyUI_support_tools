"""Display metadata for a tool, never a reference to its implementation."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolEntry:
    id: str
    label: str
    category: str
