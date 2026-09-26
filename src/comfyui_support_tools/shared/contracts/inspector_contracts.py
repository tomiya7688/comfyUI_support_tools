"""Immutable Action/Inspector messages. No widgets, handles or backend modules."""
from dataclasses import dataclass
from comfyui_support_tools.shared.contracts.media_item import MediaItem


@dataclass(frozen=True)
class ScoredLabel:
    name: str
    score: float


@dataclass(frozen=True)
class NormalizedTagResult:
    content_tags: tuple[str, ...] = ()
    character_tags: tuple[str, ...] = ()
    copyright_tags: tuple[str, ...] = ()
    rating: str = ""
    caption: str = ""
    content_scores: tuple[ScoredLabel, ...] = ()
    character_scores: tuple[ScoredLabel, ...] = ()
    rating_scores: tuple[ScoredLabel, ...] = ()
    backend: str = ""
    model: str = ""


@dataclass(frozen=True)
class MediaNotes:
    content_tags: tuple[str, ...] = ()
    style_tags: tuple[str, ...] = ()
    prompt: str = ""
    negative_prompt: str = ""
    character: str = ""
    dataset: str = ""
    character_tags: tuple[str, ...] = ()
    copyright_tags: tuple[str, ...] = ()
    rating: str = ""
    caption: str = ""
    tagger_backend: str = ""
    tagger_model: str = ""
    content_scores: tuple[ScoredLabel, ...] = ()
    character_scores: tuple[ScoredLabel, ...] = ()
    rating_scores: tuple[ScoredLabel, ...] = ()


@dataclass(frozen=True)
class TaggerSettings:
    url: str = ""
    model: str = ""
    threshold: float = 0.35
    character_threshold: float = 0.85
    timeout: float = 30.0
    backend: str = "auto_http"


@dataclass(frozen=True)
class ExportSettings:
    caption_sidecar: bool = True
    metadata_sidecar: bool = True
    batch_txt_path: str = ""
    include_style_in_caption: bool = False
    overwrite: bool = False


@dataclass(frozen=True)
class MediaExportRecord:
    item: MediaItem
    notes: MediaNotes


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
    export_settings: ExportSettings | None = None
    export_records: tuple[MediaExportRecord, ...] = ()


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
