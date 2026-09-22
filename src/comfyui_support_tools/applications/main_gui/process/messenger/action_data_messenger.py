"""Forward Action IO through the explicit UPD boundary."""
from comfyui_support_tools.applications.main_gui.data.messenger.action_messenger import ActionDataMessenger


class ActionDataRequests:
    def __init__(self, target: ActionDataMessenger):
        self._target = target

    def start(self, request):
        return self._target.start(request)

    def poll(self):
        return self._target.poll()

    def cancel(self):
        return self._target.cancel()

    def close(self):
        return self._target.close()
