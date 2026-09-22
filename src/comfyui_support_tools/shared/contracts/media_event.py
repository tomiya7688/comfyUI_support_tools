"""Worker-to-owner messages. Tokens reject stale folder/view results."""
from dataclasses import dataclass
from comfyui_support_tools.shared.contracts.media_item import MediaItem
from comfyui_support_tools.shared.contracts.media_preview import MediaPreview


@dataclass(frozen=True)
class MediaEvent:
    kind: str
    token: int
    items: tuple[MediaItem, ...] = ()
    preview: MediaPreview | None = None
    message: str = ""
