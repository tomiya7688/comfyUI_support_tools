"""Route local-media IO to its worker implementation."""
from comfyui_support_tools.applications.main_gui.data.processing.media_io import MediaIO


class MediaDataCommander:
    def __init__(self, io: MediaIO):
        self._io = io

    def scan(self, folder, collection):
        return self._io.scan(folder, collection)

    def thumbnails(self, token, items):
        return self._io.thumbnails(token, items)

    def preview(self, token, item, fraction):
        return self._io.preview(token, item, fraction)

    def poll(self):
        return self._io.poll()

    def close(self):
        self._io.close()
