"""Application-level composition template orchestration."""

from pathlib import Path

from comfyui_support_tools.applications.composition_template.process.messenger.template_library_messenger import (
    TemplateLibraryMessenger,
)
from comfyui_support_tools.applications.composition_template.process.processing.adaptation import (
    adapt_template,
)
from comfyui_support_tools.applications.composition_template.process.processing.extraction import (
    CompositionExtractionProcessor,
)
from comfyui_support_tools.applications.composition_template.process.processing.guidance import (
    export_guidance,
    export_prompt,
)
from comfyui_support_tools.shared.contracts.composition_template import (
    AspectPolicy,
    CompositionTemplate,
    DepthAnalysisAdapter,
    ExtractionLevel,
    PerspectiveAnalysisAdapter,
    PoseAnalysisAdapter,
    SubjectAnalysisAdapter,
)


# {
# 責務: [CompositionTemplateApplication: orchestrate template extraction, transformation, export and storage]
# フィールド: [extractor and Process-to-Data library messenger]
# 処理: [route composition requests between focused Process processing and Data persistence]
# }
class CompositionTemplateApplication:
    # {
    # 責務: [__init__: bind extraction and library endpoints]
    # 処理: [store injected processors and messenger]
    # 引数: [self: application, library: Process messenger, extractor: extraction processor]
    # 戻り値: [None: application initialized]
    # }
    def __init__(
        self,
        library: TemplateLibraryMessenger,
        extractor: CompositionExtractionProcessor | None = None,
    ) -> None:
        self._library = library
        self._extractor = extractor or CompositionExtractionProcessor()

    # {
    # 責務: [extract: create a template from an image]
    # 処理: [delegate extraction and optional model adapters to Process processing]
    # 引数: [source: image file, level: abstraction detail, subject_adapter: optional subject detector, pose_adapter: optional pose provider, depth_adapter: optional depth provider, perspective_adapter: optional perspective provider]
    # 戻り値: [CompositionTemplate: abstract spatial template]
    # }
    def extract(
        self,
        source: str | Path,
        level: ExtractionLevel = ExtractionLevel.LAYOUT,
        subject_adapter: SubjectAnalysisAdapter | None = None,
        pose_adapter: PoseAnalysisAdapter | None = None,
        depth_adapter: DepthAnalysisAdapter | None = None,
        perspective_adapter: PerspectiveAnalysisAdapter | None = None,
    ) -> CompositionTemplate:
        return self._extractor.extract(
            source, level, subject_adapter, pose_adapter, depth_adapter, perspective_adapter
        )

    # {
    # 責務: [adapt: adjust template geometry to a target ratio]
    # 処理: [delegate non-stretch adaptation to Process processing]
    # 引数: [template: source template, ratio: target width/height ratio, policy: fit/crop/smart reflow]
    # 戻り値: [CompositionTemplate: transformed layout]
    # }
    def adapt(
        self, template: CompositionTemplate, ratio: float, policy: AspectPolicy
    ) -> CompositionTemplate:
        return adapt_template(template, ratio, policy)

    # {
    # 責務: [prompt: create an appearance-free prompt fragment]
    # 処理: [delegate prompt formatting]
    # 引数: [template: abstract layout]
    # 戻り値: [str: spatial prompt fragment]
    # }
    def prompt(self, template: CompositionTemplate) -> str:
        return export_prompt(template)

    # {
    # 責務: [guidance: create a generation integration payload]
    # 処理: [delegate generic guidance serialization]
    # 引数: [template: abstract layout]
    # 戻り値: [str: versioned guidance JSON]
    # }
    def guidance(self, template: CompositionTemplate) -> str:
        return export_guidance(template)

    # {
    # 責務: [save: store a reusable named template]
    # 処理: [forward to Data through Process messenger]
    # 引数: [name: template identifier, template: abstract layout]
    # 戻り値: [Path: saved JSON path]
    # }
    def save(self, name: str, template: CompositionTemplate) -> Path:
        return self._library.save(name, template)

    # {
    # 責務: [load: retrieve one saved template]
    # 処理: [forward to Data through Process messenger]
    # 引数: [name: template identifier]
    # 戻り値: [CompositionTemplate: reusable layout]
    # }
    def load(self, name: str) -> CompositionTemplate:
        return self._library.load(name)

    # {
    # 責務: [list_templates: list saved templates]
    # 処理: [forward to Data through Process messenger]
    # 引数: [none]
    # 戻り値: [tuple[str, ...]: stable template names]
    # }
    def list_templates(self) -> tuple[str, ...]:
        return self._library.list_names()

    # {
    # 責務: [import_json: import a portable template document]
    # 処理: [forward decoding through Process-to-Data messenger]
    # 引数: [document: untrusted JSON template]
    # 戻り値: [CompositionTemplate: validated layout]
    # }
    def import_json(self, document: str) -> CompositionTemplate:
        return self._library.import_json(document)

    # {
    # 責務: [export_json: export a portable template document]
    # 処理: [forward encoding through Process-to-Data messenger]
    # 引数: [template: validated layout]
    # 戻り値: [str: versioned JSON document]
    # }
    def export_json(self, template: CompositionTemplate) -> str:
        return self._library.export_json(template)

    # {
    # 責務: [import_file: import a template from a chosen path]
    # 処理: [forward file handling through Process-to-Data messenger]
    # 引数: [path: template JSON path]
    # 戻り値: [CompositionTemplate: validated layout]
    # }
    def import_file(self, path: str | Path) -> CompositionTemplate:
        return self._library.import_file(path)

    # {
    # 責務: [export_file: save a template to a chosen path]
    # 処理: [forward file handling through Process-to-Data messenger]
    # 引数: [path: output JSON path, template: validated layout]
    # 戻り値: [Path: exported file]
    # }
    def export_file(self, path: str | Path, template: CompositionTemplate) -> Path:
        return self._library.export_file(path, template)

    # {
    # 責務: [export_guidance_file: write a generic generation guidance artifact]
    # 処理: [format guidance in Process and send generated text through the Data messenger]
    # 引数: [path: output path, template: abstract layout]
    # 戻り値: [Path: exported guidance file]
    # }
    def export_guidance_file(self, path: str | Path, template: CompositionTemplate) -> Path:
        return self._library.write_document(path, export_guidance(template))
