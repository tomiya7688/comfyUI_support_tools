"""Transport media IO requests/results without interpreting their contents."""
from comfyui_support_tools.applications.main_gui.data.messenger.media_messenger import MediaDataMessenger


class MediaDataRequests:
    def __init__(self, target: MediaDataMessenger):
        self._target = target

    def scan(self, folder, collection):
        return self._target.scan(folder, collection)

    def thumbnails(self, token, items):
        return self._target.thumbnails(token, items)

    def preview(self, token, item, fraction):
        return self._target.preview(token, item, fraction)

    def poll(self):
        return self._target.poll()

    def close(self):
        return self._target.close()
