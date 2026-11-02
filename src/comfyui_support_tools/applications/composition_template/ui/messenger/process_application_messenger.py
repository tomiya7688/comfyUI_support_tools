"""Transport UI requests to the Process application endpoint."""

from pathlib import Path
from typing import Protocol

from comfyui_support_tools.shared.contracts.composition_template import (
    AspectPolicy,
    CompositionTemplate,
    ExtractionLevel,
)


# {
# 責務: [ProcessApplicationEndpoint: describe commands available to the UI boundary]
# 処理: [declare the Process application operations without importing its implementation]
# }
class ProcessApplicationEndpoint(Protocol):
    # {
    # 責務: [extract: expose the Process extraction operation]
    # 処理: [accept an image source and abstraction level]
    # }
    def extract(
        self, source: str | Path, level: ExtractionLevel = ExtractionLevel.LAYOUT
    ) -> CompositionTemplate: ...

    # {
    # 責務: [adapt: expose the Process geometry transformation]
    # 処理: [accept a template, target ratio and policy]
    # }
    def adapt(
        self, template: CompositionTemplate, ratio: float, policy: AspectPolicy
    ) -> CompositionTemplate: ...

    # {
    # 責務: [prompt: expose spatial prompt generation]
    # 処理: [accept an abstract template]
    # }
    def prompt(self, template: CompositionTemplate) -> str: ...

    # {
    # 責務: [guidance: expose generic generation guidance]
    # 処理: [accept an abstract template]
    # }
    def guidance(self, template: CompositionTemplate) -> str: ...

    # {
    # 責務: [save: expose template library persistence]
    # 処理: [accept an identifier and abstract template]
    # }
    def save(self, name: str, template: CompositionTemplate) -> Path: ...

    # {
    # 責務: [load: expose template library retrieval]
    # 処理: [accept a template identifier]
    # }
    def load(self, name: str) -> CompositionTemplate: ...

    # {
    # 責務: [list_templates: expose template library listing]
    # 処理: [return available template identifiers]
    # }
    def list_templates(self) -> tuple[str, ...]: ...

    # {
    # 責務: [import_file: expose versioned JSON template import]
    # 処理: [accept a selected template file path]
    # }
    def import_file(self, path: str | Path) -> CompositionTemplate: ...

    # {
    # 責務: [export_file: expose versioned JSON template export]
    # 処理: [accept a destination path and template]
    # }
    def export_file(self, path: str | Path, template: CompositionTemplate) -> Path: ...

    # {
    # 責務: [export_guidance_file: expose generation guidance export]
    # 処理: [accept a destination path and template]
    # }
    def export_guidance_file(self, path: str | Path, template: CompositionTemplate) -> Path: ...


# {
# 責務: [ProcessApplicationMessenger: carry UI operations to the Process endpoint]
# フィールド: [injected Process application endpoint]
# 処理: [forward requests without interpreting template business data]
# }
class ProcessApplicationMessenger:
    # {
    # 責務: [__init__: bind the Process-side application endpoint]
    # 処理: [store the injectable Process endpoint]
    # 引数: [self: UI messenger, target: Process application endpoint]
    # 戻り値: [None: messenger initialized]
    # }
    def __init__(self, target: ProcessApplicationEndpoint) -> None:
        self._target = target

    # {
    # 責務: [extract: send an image extraction request]
    # 処理: [forward the image path and abstraction level]
    # 引数: [source: image path, level: abstraction level]
    # 戻り値: [CompositionTemplate: extracted template]
    # }
    def extract(
        self, source: str | Path, level: ExtractionLevel = ExtractionLevel.LAYOUT
    ) -> CompositionTemplate:
        return self._target.extract(source, level)

    # {
    # 責務: [adapt: send an aspect-ratio adaptation request]
    # 処理: [forward template, ratio, and policy]
    # 引数: [template: layout, ratio: target aspect, policy: transform policy]
    # 戻り値: [CompositionTemplate: transformed template]
    # }
    def adapt(
        self, template: CompositionTemplate, ratio: float, policy: AspectPolicy
    ) -> CompositionTemplate:
        return self._target.adapt(template, ratio, policy)

    # {
    # 責務: [prompt: request prompt text]
    # 処理: [forward the template]
    # 引数: [template: layout]
    # 戻り値: [str: prompt fragment]
    # }
    def prompt(self, template: CompositionTemplate) -> str:
        return self._target.prompt(template)

    # {
    # 責務: [guidance: request generation guidance]
    # 処理: [forward the template]
    # 引数: [template: layout]
    # 戻り値: [str: guidance document]
    # }
    def guidance(self, template: CompositionTemplate) -> str:
        return self._target.guidance(template)

    # {
    # 責務: [save: request library persistence]
    # 処理: [forward name and template]
    # 引数: [name: identifier, template: layout]
    # 戻り値: [Path: saved template path]
    # }
    def save(self, name: str, template: CompositionTemplate) -> Path:
        return self._target.save(name, template)

    # {
    # 責務: [load: request library retrieval]
    # 処理: [forward the identifier]
    # 引数: [name: identifier]
    # 戻り値: [CompositionTemplate: stored layout]
    # }
    def load(self, name: str) -> CompositionTemplate:
        return self._target.load(name)

    # {
    # 責務: [list_templates: request available library identifiers]
    # 処理: [forward the listing request]
    # 引数: [none]
    # 戻り値: [tuple[str, ...]: stored identifiers]
    # }
    def list_templates(self) -> tuple[str, ...]:
        return self._target.list_templates()

    # {
    # 責務: [import_file: request template file import]
    # 処理: [forward the selected path]
    # 引数: [path: JSON path]
    # 戻り値: [CompositionTemplate: validated layout]
    # }
    def import_file(self, path: str | Path) -> CompositionTemplate:
        return self._target.import_file(path)

    # {
    # 責務: [export_file: request template file export]
    # 処理: [forward the path and layout]
    # 引数: [path: destination path, template: layout]
    # 戻り値: [Path: exported file]
    # }
    def export_file(self, path: str | Path, template: CompositionTemplate) -> Path:
        return self._target.export_file(path, template)

    # {
    # 責務: [export_guidance_file: request generation guidance export]
    # 処理: [forward the path and layout]
    # 引数: [path: destination path, template: layout]
    # 戻り値: [Path: exported file]
    # }
    def export_guidance_file(self, path: str | Path, template: CompositionTemplate) -> Path:
        return self._target.export_guidance_file(path, template)
