"""Bounded preview payload; never contains a Tk image or an open file handle."""

from dataclasses import dataclass


# {
# 責務: [MediaPreview: itemに紐づくbounded preview bytesと寸法、durationまたはerror]
# フィールド: [item_id, png, width, height, duration, error]
# }
@dataclass(frozen=True)
class MediaPreview:
    item_id: str
    png: bytes = b""
    width: int = 0
    height: int = 0
    duration: float = 0.0
    error: str = ""
