"""Transport Inspector messages without interpreting their contents."""
from comfyui_support_tools.applications.main_gui.ui.messenger.inspector_messenger import InspectorUiMessenger


class InspectorUiCommander:
    def __init__(self, target: InspectorUiMessenger):
        self._target = target

    def configure(self, settings):
        return self._target.configure(settings)

    def select(self, items):
        return self._target.select(items)

    def options(self):
        return self._target.options()

    def notes(self):
        return self._target.notes()

    def save_notes(self, notes):
        return self._target.save_notes(notes)

    def status(self):
        return self._target.status()

    def start(self, kind):
        return self._target.start(kind)

    def export(self, settings):
        return self._target.export(settings)

    def poll(self):
        return self._target.poll()

    def cancel(self):
        return self._target.cancel()

    def close(self):
        return self._target.close()
