"""Forward Action IO through the explicit UPD boundary."""
from comfyui_support_tools.applications.main_gui.data.commander.action_commander import ActionDataCommander


class ActionDataMessenger:
    def __init__(self, target: ActionDataCommander):
        self._target = target

    def start(self, request):
        return self._target.start(request)

    def poll(self):
        return self._target.poll()

    def cancel(self):
        return self._target.cancel()

    def close(self):
        return self._target.close()
