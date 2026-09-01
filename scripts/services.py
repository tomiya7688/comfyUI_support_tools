from __future__ import annotations

import atexit

from .backend.comfy_ui_client import ComfyUIClient
from .backend.embedded_random_image import EmbeddedRandomImage
from .backend.embedded_start_webui import EmbeddedStartWebUI
from .backend.pixai_tagger_server import PixAITaggerServer
from .widgets.labeled_path_row import LabeledPathRow
from .widgets.log_box import LogBox


PIXAI_TAGGER_SERVER = PixAITaggerServer()
atexit.register(PIXAI_TAGGER_SERVER.stop)
EMBEDDED_START_WEBUI = EmbeddedStartWebUI()
EMBEDDED_RANDOM_IMAGE = EmbeddedRandomImage()

__all__ = [
    "ComfyUIClient", "EmbeddedRandomImage", "EmbeddedStartWebUI",
    "PixAITaggerServer", "LabeledPathRow", "LogBox",
    "PIXAI_TAGGER_SERVER", "EMBEDDED_START_WEBUI",
    "EMBEDDED_RANDOM_IMAGE",
]
