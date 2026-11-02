"""Route editor actions through the UI-to-Process messenger."""

from pathlib import Path

from comfyui_support_tools.applications.composition_template.ui.messenger.process_application_messenger import (
    ProcessApplicationMessenger,
)
from comfyui_support_tools.shared.contracts.composition_template import (
    AspectPolicy,
    CompositionTemplate,
    ExtractionLevel,
)


# {
# 責務: [CompositionTemplateUiCommander: route UI actions to Process communication]
# フィールド: [Process application messenger]
# 処理: [expose editor operations while keeping UI processing independent from Process internals]
# }
class CompositionTemplateUiCommander:
    # {
    # 責務: [__init__: bind the UI messenger]
    # 処理: [store the Process communication endpoint]
    # 引数: [self: UI commander, messenger: Process application messenger]
    # 戻り値: [None: commander initialized]
    # }
    def __init__(self, messenger: ProcessApplicationMessenger) -> None:
        self._messenger = messenger

    # {
    # 責務: [extract: route image extraction]
    # 処理: [send image path and level through the UI messenger]
    # 引数: [source: image path, level: abstraction level]
    # 戻り値: [CompositionTemplate: extracted layout]
    # }
    def extract(
        self, source: str | Path, level: ExtractionLevel = ExtractionLevel.LAYOUT
    ) -> CompositionTemplate:
        return self._messenger.extract(source, level)

    # {
    # 責務: [adapt: route aspect-ratio transformation]
    # 処理: [send template and policy through the UI messenger]
    # 引数: [template: layout, ratio: target ratio, policy: adaptation policy]
    # 戻り値: [CompositionTemplate: adapted layout]
    # }
    def adapt(
        self, template: CompositionTemplate, ratio: float, policy: AspectPolicy
    ) -> CompositionTemplate:
        return self._messenger.adapt(template, ratio, policy)

    # {
    # 責務: [prompt: route prompt generation]
    # 処理: [request Process prompt formatting]
    # 引数: [template: layout]
    # 戻り値: [str: prompt fragment]
    # }
    def prompt(self, template: CompositionTemplate) -> str:
        return self._messenger.prompt(template)

    # {
    # 責務: [save: route library persistence]
    # 処理: [send template and name through the UI messenger]
    # 引数: [name: identifier, template: layout]
    # 戻り値: [Path: saved path]
    # }
    def save(self, name: str, template: CompositionTemplate) -> Path:
        return self._messenger.save(name, template)

    # {
    # 責務: [load: route library retrieval]
    # 処理: [request a stored template through the UI messenger]
    # 引数: [name: identifier]
    # 戻り値: [CompositionTemplate: stored layout]
    # }
    def load(self, name: str) -> CompositionTemplate:
        return self._messenger.load(name)

    # {
    # 責務: [list_templates: route library listing]
    # 処理: [request available template names]
    # 引数: [none]
    # 戻り値: [tuple[str, ...]: available names]
    # }
    def list_templates(self) -> tuple[str, ...]:
        return self._messenger.list_templates()

    # {
    # 責務: [import_file: route JSON template import]
    # 処理: [request Data-backed import through the messenger]
    # 引数: [path: JSON path]
    # 戻り値: [CompositionTemplate: imported layout]
    # }
    def import_file(self, path: str | Path) -> CompositionTemplate:
        return self._messenger.import_file(path)

    # {
    # 責務: [export_file: route JSON template export]
    # 処理: [request Data-backed export through the messenger]
    # 引数: [path: destination path, template: layout]
    # 戻り値: [Path: exported path]
    # }
    def export_file(self, path: str | Path, template: CompositionTemplate) -> Path:
        return self._messenger.export_file(path, template)

    # {
    # 責務: [export_guidance_file: route generation guidance export]
    # 処理: [request Process formatting and Data file output through the messenger]
    # 引数: [path: destination path, template: layout]
    # 戻り値: [Path: exported path]
    # }
    def export_guidance_file(self, path: str | Path, template: CompositionTemplate) -> Path:
        return self._messenger.export_guidance_file(path, template)
