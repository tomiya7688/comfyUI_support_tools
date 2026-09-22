"""Composition only; the Tagger itself is an external HTTP service."""
from comfyui_support_tools.applications.main_gui.data.processing.action_io import ActionIO
from comfyui_support_tools.applications.main_gui.data.commander.action_commander import ActionDataCommander
from comfyui_support_tools.applications.main_gui.data.messenger.action_messenger import ActionDataMessenger
from comfyui_support_tools.applications.main_gui.process.messenger.action_data_messenger import ActionDataRequests
from comfyui_support_tools.applications.main_gui.process.processing.inspector_state import InspectorState
from comfyui_support_tools.applications.main_gui.process.commander.inspector_commander import InspectorCommander
from comfyui_support_tools.applications.main_gui.process.messenger.inspector_messenger import InspectorProcessMessenger
from comfyui_support_tools.applications.main_gui.ui.messenger.inspector_messenger import InspectorUiMessenger
from comfyui_support_tools.applications.main_gui.ui.commander.inspector_commander import InspectorUiCommander


def create_inspector():
    data = ActionDataRequests(ActionDataMessenger(ActionDataCommander(ActionIO())))
    process = InspectorProcessMessenger(InspectorCommander(InspectorState(), data))
    return InspectorUiCommander(InspectorUiMessenger(process))
