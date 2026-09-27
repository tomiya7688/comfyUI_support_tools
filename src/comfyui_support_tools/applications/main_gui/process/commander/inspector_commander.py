"""Route commands; session rules and IO belong to their Processing components."""
from comfyui_support_tools.applications.main_gui.process.processing.inspector_state import InspectorState
from comfyui_support_tools.applications.main_gui.process.messenger.action_data_messenger import ActionDataRequests


class InspectorCommander:
    def __init__(self, state: InspectorState, data: ActionDataRequests):
        self._state = state
        self._data = data

    def configure(self, settings):
        return self._state.configure(settings)

    def select(self, items):
        return self._state.select(items)

    def options(self):
        return self._state.options()

    def notes(self):
        return self._state.current_notes()

    def save_notes(self, notes):
        return self._state.save_notes(notes)

    def status(self):
        return self._state.status()

    def start(self, kind):
        return self._start_request(self._state.begin(kind))

    def export(self, settings):
        return self._start_request(self._state.begin_export(settings))

    def _start_request(self, request):
        try:
            self._data.start(request)
        except Exception:
            self._state.failed_start()
            raise

    def poll(self):
        return self._state.accept(self._data.poll())

    def cancel(self):
        return self._data.cancel()

    def close(self):
        return self._data.close()
