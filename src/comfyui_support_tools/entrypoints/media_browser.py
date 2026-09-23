"""Main GUI media-browser composition; does not import legacy/backend apps."""
from comfyui_support_tools.applications.main_gui.data.processing.media_io import MediaIO
from comfyui_support_tools.applications.main_gui.data.commander.media_commander import MediaDataCommander
from comfyui_support_tools.applications.main_gui.data.messenger.media_messenger import MediaDataMessenger
from comfyui_support_tools.applications.main_gui.process.messenger.media_data_messenger import MediaDataRequests
from comfyui_support_tools.applications.main_gui.process.processing.media_session import MediaSession
from comfyui_support_tools.applications.main_gui.process.commander.media_commander import MediaCommander
from comfyui_support_tools.applications.main_gui.process.messenger.media_messenger import MediaProcessMessenger
from comfyui_support_tools.applications.main_gui.ui.messenger.media_messenger import MediaUiMessenger
from comfyui_support_tools.applications.main_gui.ui.commander.media_commander import MediaUiCommander


def create_media_browser(jobs=None) -> MediaUiCommander:
    data = MediaDataRequests(MediaDataMessenger(MediaDataCommander(MediaIO(jobs))))
    process = MediaProcessMessenger(MediaCommander(MediaSession(), data))
    return MediaUiCommander(MediaUiMessenger(process))
