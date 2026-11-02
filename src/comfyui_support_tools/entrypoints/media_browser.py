"""Main GUI media-browser composition; does not import legacy/backend apps."""

from comfyui_support_tools.applications.main_gui.data.processing.media_io import MediaIO
from comfyui_support_tools.applications.main_gui.data.commander.media_commander import (
    MediaDataCommander,
)
from comfyui_support_tools.applications.main_gui.data.messenger.media_messenger import (
    MediaDataMessenger,
)
from comfyui_support_tools.applications.main_gui.process.messenger.media_data_messenger import (
    MediaDataRequests,
)
from comfyui_support_tools.applications.main_gui.process.processing.media_session import (
    MediaSession,
)
from comfyui_support_tools.applications.main_gui.process.commander.media_commander import (
    MediaCommander,
)
from comfyui_support_tools.applications.main_gui.process.messenger.media_messenger import (
    MediaProcessMessenger,
)
from comfyui_support_tools.applications.main_gui.ui.messenger.media_messenger import (
    MediaUiMessenger,
)
from comfyui_support_tools.applications.main_gui.ui.commander.media_commander import (
    MediaUiCommander,
)


# {
#   責務: [create_media_browser: media I/O/session/process/UI層を接続してbrowser commanderを構築する]
#   処理: [optional jobs runtimeをMediaIOへ注入し、media scan/preview requestを経由する層をcomposeする]
#   引数: [jobs: optional shared job runtime]
#   戻り値: [MediaUiCommander: media browser UI操作入口]
# }
def create_media_browser(jobs=None) -> MediaUiCommander:
    data = MediaDataRequests(MediaDataMessenger(MediaDataCommander(MediaIO(jobs))))
    process = MediaProcessMessenger(MediaCommander(MediaSession(), data))
    return MediaUiCommander(MediaUiMessenger(process))
