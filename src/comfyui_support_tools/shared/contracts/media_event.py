"""Worker-to-owner messages. Tokens reject stale folder/view results."""

from dataclasses import dataclass
from comfyui_support_tools.shared.contracts.media_item import MediaItem
from comfyui_support_tools.shared.contracts.media_preview import MediaPreview


# {
# 責務: [MediaEvent: worker結果をtoken付きでownerへ渡し、古いview結果を識別する]
# フィールド: [kind, token, items, preview, message]
# }
@dataclass(frozen=True)
class MediaEvent:
    kind: str
    token: int
    items: tuple[MediaItem, ...] = ()
    preview: MediaPreview | None = None
    message: str = ""
