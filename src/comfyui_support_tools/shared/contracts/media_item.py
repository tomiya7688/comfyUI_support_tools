"""Stable, framework-neutral media identity and selection contract."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaItem:
    id: str
    path: str
    name: str
    kind: str
    collection: str
    size: int
    modified_ns: int
