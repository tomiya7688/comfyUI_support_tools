"""Immutable Action/Inspector messages. No widgets, handles or backend modules."""
from dataclasses import dataclass
from comfyui_support_tools.shared.contracts.media_item import MediaItem


@dataclass(frozen=True)
class MediaNotes:
    content_tags: tuple[str, ...] = ()
    style_tags: tuple[str, ...] = ()
    prompt: str = ""
    negative_prompt: str = ""
    character: str = ""
    dataset: str = ""


@dataclass(frozen=True)
class TaggerSettings:
    url: str = ""
    model: str = ""
    threshold: float = 0.35
    character_threshold: float = 0.85
    timeout: float = 30.0


@dataclass(frozen=True)
class ActionDefinition:
    id: str
    label: str
    kinds: tuple[str, ...]
    unavailable: str = ""


@dataclass(frozen=True)
class ActionAvailability:
    definition: ActionDefinition
    enabled: bool
    reason: str = ""


@dataclass(frozen=True)
class ActionRequest:
    token: int
    kind: str
    settings: TaggerSettings
    items: tuple[MediaItem, ...] = ()


@dataclass(frozen=True)
class ActionEvent:
    token: int
    kind: str
    item: MediaItem | None = None
    tags: tuple[str, ...] = ()
    models: tuple[str, ...] = ()
    message: str = ""
    failed: bool = False


@dataclass(frozen=True)
class InspectorStatus:
    settings: TaggerSettings
    models: tuple[str, ...]
    busy: bool
    ready: bool
    message: str
