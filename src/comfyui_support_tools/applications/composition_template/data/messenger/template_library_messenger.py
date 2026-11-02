"""Data endpoint for composition template library operations."""

from pathlib import Path

from comfyui_support_tools.applications.composition_template.data.processing.codec import (
    template_from_json,
    template_to_json,
)
from comfyui_support_tools.applications.composition_template.data.processing.library import (
    TemplateLibrary,
)
from comfyui_support_tools.shared.contracts.composition_template import CompositionTemplate


# {
# 責務: [TemplateLibraryMessenger: serve template storage requests]
# 処理: [delegate list, save, and load operations to Data processing]
# }
class TemplateLibraryMessenger:
    # {
    # 責務: [__init__: bind the Data library endpoint]
    # 処理: [construct the user-selected filesystem library]
    # 引数: [self: Data endpoint, root: library directory]
    # 戻り値: [None: Data endpoint initialized]
    # }
    def __init__(self, root: str | Path) -> None:
        self._library = TemplateLibrary(root)

    # {
    # 責務: [list_names: return saved template names]
    # 処理: [delegate to Data library storage]
    # }
    def list_names(self) -> tuple[str, ...]:
        return self._library.list_names()

    # {
    # 責務: [save: persist one named template]
    # 処理: [delegate to Data library storage]
    # }
    def save(self, name: str, template: CompositionTemplate) -> Path:
        return self._library.save(name, template)

    # {
    # 責務: [load: retrieve one named template]
    # 処理: [delegate to Data library storage]
    # }
    def load(self, name: str) -> CompositionTemplate:
        return self._library.load(name)

    # {
    # 責務: [import_json: parse a portable template document]
    # 処理: [delegate versioned parsing to Data processing]
    # }
    def import_json(self, document: str) -> CompositionTemplate:
        return template_from_json(document)

    # {
    # 責務: [export_json: serialize a template for file export]
    # 処理: [delegate versioned JSON conversion to Data processing]
    # }
    def export_json(self, template: CompositionTemplate) -> str:
        return template_to_json(template)

    # {
    # 責務: [import_file: load and validate a template file]
    # 処理: [bound the input size and delegate JSON conversion]
    # 引数: [path: selected JSON path]
    # 戻り値: [CompositionTemplate: validated template]
    # }
    def import_file(self, path: str | Path) -> CompositionTemplate:
        source = Path(path)
        if source.is_symlink() or not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("template file is missing or exceeds the 2 MiB limit")
        return template_from_json(source.read_text(encoding="utf-8"))

    # {
    # 責務: [export_file: write a versioned template JSON file]
    # 処理: [serialize via Data processing and write the user-selected file]
    # 引数: [path: output JSON path, template: validated template]
    # 戻り値: [Path: exported JSON path]
    # }
    def export_file(self, path: str | Path, template: CompositionTemplate) -> Path:
        destination = Path(path)
        destination.write_text(template_to_json(template), encoding="utf-8")
        return destination

    # {
    # 責務: [write_document: write a generated text artifact]
    # 処理: [bound the document size and write UTF-8 text to a user-selected path]
    # 引数: [path: destination path, document: generated content]
    # 戻り値: [Path: written document]
    # }
    def write_document(self, path: str | Path, document: str) -> Path:
        if len(document.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("export document exceeds the 2 MiB limit")
        destination = Path(path)
        destination.write_text(document, encoding="utf-8")
        return destination
