"""Process endpoint for template library messages."""

from pathlib import Path

from comfyui_support_tools.applications.composition_template.data.messenger.template_library_messenger import (
    TemplateLibraryMessenger as DataLibraryEndpoint,
)
from comfyui_support_tools.shared.contracts.composition_template import CompositionTemplate


# {
# 責務: [TemplateLibraryMessenger: route Process requests to Data]
# 処理: [forward template library payloads without storage logic]
# }
class TemplateLibraryMessenger:
    # {
    # 責務: [__init__: bind the Data-side messenger endpoint]
    # 処理: [store an injectable Data messenger target]
    # 引数: [self: Process messenger, target: Data messenger endpoint]
    # 戻り値: [None: endpoint bound]
    # }
    def __init__(self, target: DataLibraryEndpoint) -> None:
        self._target = target

    # {
    # 責務: [list_names: transport a list request]
    # 処理: [forward to Data messenger]
    # }
    def list_names(self) -> tuple[str, ...]:
        return self._target.list_names()

    # {
    # 責務: [save: transport a template save request]
    # 処理: [forward to Data messenger]
    # }
    def save(self, name: str, template: CompositionTemplate) -> Path:
        return self._target.save(name, template)

    # {
    # 責務: [load: transport a template load request]
    # 処理: [forward to Data messenger]
    # }
    def load(self, name: str) -> CompositionTemplate:
        return self._target.load(name)

    # {
    # 責務: [import_json: transport a template document for decoding]
    # 処理: [forward to Data messenger]
    # }
    def import_json(self, document: str) -> CompositionTemplate:
        return self._target.import_json(document)

    # {
    # 責務: [export_json: transport a template for encoding]
    # 処理: [forward to Data messenger]
    # }
    def export_json(self, template: CompositionTemplate) -> str:
        return self._target.export_json(template)

    # {
    # 責務: [import_file: transport a template file import request]
    # 処理: [forward to Data messenger]
    # 引数: [path: selected JSON path]
    # 戻り値: [CompositionTemplate: validated template]
    # }
    def import_file(self, path: str | Path) -> CompositionTemplate:
        return self._target.import_file(path)

    # {
    # 責務: [export_file: transport a template file export request]
    # 処理: [forward to Data messenger]
    # 引数: [path: output JSON path, template: validated template]
    # 戻り値: [Path: exported JSON path]
    # }
    def export_file(self, path: str | Path, template: CompositionTemplate) -> Path:
        return self._target.export_file(path, template)

    # {
    # 責務: [write_document: transport generated text for file output]
    # 処理: [forward the path and document to Data messenger]
    # 引数: [path: destination path, document: generated content]
    # 戻り値: [Path: written document]
    # }
    def write_document(self, path: str | Path, document: str) -> Path:
        return self._target.write_document(path, document)
