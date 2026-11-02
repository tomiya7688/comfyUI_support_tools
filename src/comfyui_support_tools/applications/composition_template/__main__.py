"""Launch the composition template editor."""

from pathlib import Path

from comfyui_support_tools.applications.composition_template.data.messenger.template_library_messenger import (
    TemplateLibraryMessenger as DataLibraryMessenger,
)
from comfyui_support_tools.applications.composition_template.process.commander.application import (
    CompositionTemplateApplication,
)
from comfyui_support_tools.applications.composition_template.process.messenger.template_library_messenger import (
    TemplateLibraryMessenger as ProcessLibraryMessenger,
)
from comfyui_support_tools.applications.composition_template.ui.commander.application import (
    CompositionTemplateUiCommander,
)
from comfyui_support_tools.applications.composition_template.ui.messenger.process_application_messenger import (
    ProcessApplicationMessenger,
)
from comfyui_support_tools.applications.composition_template.ui.processing.window import launch

if __name__ == "__main__":
    data_library = DataLibraryMessenger(
        Path.home() / ".comfyui_support_tools" / "composition_templates"
    )
    process_library = ProcessLibraryMessenger(data_library)
    process_application = CompositionTemplateApplication(process_library)
    ui_messenger = ProcessApplicationMessenger(process_application)
    launch(CompositionTemplateUiCommander(ui_messenger))
