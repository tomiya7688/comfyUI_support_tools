"""Stable, framework-neutral media identity and selection contract."""

from dataclasses import dataclass


# {
# 責務: [MediaItem: framework非依存のmedia identity、path、kind、collection情報]
# フィールド: [id, path, name, kind, collection, size, modified_ns]
# }
@dataclass(frozen=True)
class MediaItem:
    id: str
    path: str
    name: str
    kind: str
    collection: str
    size: int
    modified_ns: int
