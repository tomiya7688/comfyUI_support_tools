"""Bounded preview payload; never contains a Tk image or an open file handle."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaPreview:
    item_id: str
    png: bytes = b""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    error: str = ""
