"""Forward media requests over the explicit UPD boundary."""
from comfyui_support_tools.applications.main_gui.process.commander.media_commander import MediaCommander


class MediaProcessMessenger:
    def __init__(self, target: MediaCommander):
        self._target = target

    def load(self, folder, collection):
        return self._target.load(folder, collection)

    def poll(self):
        return self._target.poll()

    def view(self):
        return self._target.view()

    def query(self, section, text, sort, descending):
        return self._target.query(section, text, sort, descending)

    def move_page(self, delta):
        return self._target.move_page(delta)

    def select(self, keys):
        return self._target.select(keys)

    def selection(self):
        return self._target.selection()

    def toggle_favorites(self):
        return self._target.toggle_favorites()

    def thumbnails(self, token, enabled=True):
        return self._target.thumbnails(token, enabled)

    def preview(self, token, fraction):
        return self._target.preview(token, fraction)

    def close(self):
        return self._target.close()
