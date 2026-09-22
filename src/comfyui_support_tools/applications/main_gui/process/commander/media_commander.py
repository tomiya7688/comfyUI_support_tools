"""Coordinate query state and asynchronous Data requests; no filesystem/Tk work."""
from comfyui_support_tools.applications.main_gui.process.messenger.media_data_messenger import MediaDataRequests
from comfyui_support_tools.applications.main_gui.process.processing.media_session import MediaSession


class MediaCommander:
    def __init__(self, state: MediaSession, data: MediaDataRequests):
        self._state = state
        self._data = data

    def load(self, folder, collection):
        token = self._data.scan(folder, collection)
        self._state.begin(token)

    def poll(self):
        events = self._data.poll()
        changed = self._state.accept(events)
        return changed, events

    def view(self):
        items = self._state.page_items()
        return items, self._state.summary()

    def query(self, section, text, sort, descending):
        self._state.query(section, text, sort, descending)

    def move_page(self, delta):
        self._state.move_page(delta)

    def select(self, keys):
        return self._state.select(keys)

    def selection(self):
        return self._state.selection()

    def toggle_favorites(self):
        self._state.toggle_favorites()

    def thumbnails(self, token, enabled=True):
        return self._data.thumbnails(token, self._state.page_items() if enabled else ())

    def preview(self, token, fraction):
        selection = self._state.selection()
        if selection:
            self._data.preview(token, selection[0], fraction)

    def close(self):
        self._data.close()
