"""Launch the storyboard-first Manga Creator editor."""

import os
from pathlib import Path

from comfyui_support_tools.applications.manga_creator.data.messenger.project_messenger import (
    MangaProjectMessenger as DataMessenger,
)
from comfyui_support_tools.applications.manga_creator.data.processing.comfyui_backend import (
    ComfyUIPanelBackend,
)
from comfyui_support_tools.applications.manga_creator.process.commander.application import (
    MangaCreatorApplication,
)
from comfyui_support_tools.applications.manga_creator.process.messenger.project_messenger import (
    MangaProjectMessenger as ProcessMessenger,
)
from comfyui_support_tools.applications.manga_creator.process.processing.production import (
    MangaProductionProcessor,
)
from comfyui_support_tools.applications.manga_creator.ui.commander.application import (
    MangaCreatorUiCommander,
)
from comfyui_support_tools.applications.manga_creator.ui.messenger.process_messenger import (
    MangaProcessMessenger,
)
from comfyui_support_tools.applications.manga_creator.ui.processing.window import launch

if __name__ == "__main__":
    data_endpoint = DataMessenger()
    process_messenger = ProcessMessenger(data_endpoint)
    production = MangaProductionProcessor(process_messenger)
    workflow = os.environ.get("COMFYUI_MANGA_WORKFLOW", "").strip()
    if workflow:
        production.register_backend(
            "comfyui",
            ComfyUIPanelBackend(
                Path(workflow).expanduser(),
                api_url=os.environ.get("COMFYUI_API_URL", "http://127.0.0.1:8188"),
            ),
        )
    process_application = MangaCreatorApplication(production)
    ui_messenger = MangaProcessMessenger(process_application)
    launch(MangaCreatorUiCommander(ui_messenger))
