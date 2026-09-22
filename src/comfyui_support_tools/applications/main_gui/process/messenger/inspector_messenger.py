"""Transport Inspector messages without interpreting their contents."""
from comfyui_support_tools.applications.main_gui.process.commander.inspector_commander import InspectorCommander


class InspectorProcessMessenger:
    def __init__(self, target: InspectorCommander):
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

    def poll(self):
        return self._target.poll()

    def cancel(self):
        return self._target.cancel()

    def close(self):
        return self._target.close()
