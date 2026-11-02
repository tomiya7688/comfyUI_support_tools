"""Composition only; the Tagger itself is an external HTTP service."""

from comfyui_support_tools.applications.main_gui.data.processing.action_io import ActionIO
from comfyui_support_tools.applications.main_gui.data.commander.action_commander import (
    ActionDataCommander,
)
from comfyui_support_tools.applications.main_gui.data.messenger.action_messenger import (
    ActionDataMessenger,
)
from comfyui_support_tools.applications.main_gui.process.messenger.action_data_messenger import (
    ActionDataRequests,
)
from comfyui_support_tools.applications.main_gui.process.processing.inspector_state import (
    InspectorState,
)
from comfyui_support_tools.applications.main_gui.process.commander.inspector_commander import (
    InspectorCommander,
)
from comfyui_support_tools.applications.main_gui.process.messenger.inspector_messenger import (
    InspectorProcessMessenger,
)
from comfyui_support_tools.applications.main_gui.ui.messenger.inspector_messenger import (
    InspectorUiMessenger,
)
from comfyui_support_tools.applications.main_gui.ui.commander.inspector_commander import (
    InspectorUiCommander,
)


# {
#   責務: [create_inspector: data/process/UI commanderを接続してInspector boundaryを構築する]
#   処理: [optional shared jobsをActionIOへ渡し、Tagger状態、data request、messengerを順にcomposeする]
#   引数: [jobs: optional shared job runtime]
#   戻り値: [InspectorUiCommander: UIからInspector actionを操作する入口]
# }
def create_inspector(jobs=None):
    data = ActionDataRequests(ActionDataMessenger(ActionDataCommander(ActionIO(jobs=jobs))))
    process = InspectorProcessMessenger(InspectorCommander(InspectorState(), data))
    return InspectorUiCommander(InspectorUiMessenger(process))
