"""Filesystem storage for reusable composition templates."""

from __future__ import annotations

import os
import re
from pathlib import Path

from comfyui_support_tools.shared.contracts.composition_template import CompositionTemplate

from .codec import template_from_json, template_to_json

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


# {
# 責務: [TemplateLibrary: store validated abstract templates in a chosen directory]
# フィールド: [root: user-selected library directory]
# 処理: [list, save, and load only bounded JSON template files]
# 引数: [root: library directory]
# 戻り値: [TemplateLibrary: filesystem-backed template library]
# }
class TemplateLibrary:
    # {
    # 責務: [__init__: bind the user-selected library location]
    # 処理: [resolve and store the template directory path]
    # 引数: [self: library, root: library directory]
    # 戻り値: [None: library initialized]
    # }
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    # {
    # 責務: [list_names: list valid template identifiers in stable order]
    # 処理: [ignore directories, links, and unrelated file names]
    # 引数: [self: template library]
    # 戻り値: [tuple[str, ...]: available template names]
    # }
    def list_names(self) -> tuple[str, ...]:
        if not self.root.exists():
            return ()
        return tuple(
            sorted(
                path.stem
                for path in self.root.glob("*.json")
                if path.is_file() and not path.is_symlink() and _SAFE_NAME.fullmatch(path.stem)
            )
        )

    # {
    # 責務: [save: write a template without overwriting an existing item]
    # 処理: [validate the name and atomically create a new UTF-8 JSON file]
    # 引数: [self: template library, name: safe identifier, template: validated template]
    # 戻り値: [Path: saved template path]
    # }
    def save(self, name: str, template: CompositionTemplate) -> Path:
        if not _SAFE_NAME.fullmatch(name):
            raise ValueError("template name must use 1-64 letters, digits, underscores, or hyphens")
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.root / f"{name}.json"
        encoded = template_to_json(template).encode("utf-8")
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return destination

    # {
    # 責務: [load: load a named template from the library]
    # 処理: [validate the name, reject links and oversized files, and parse the versioned schema]
    # 引数: [self: template library, name: safe identifier]
    # 戻り値: [CompositionTemplate: loaded template]
    # }
    def load(self, name: str) -> CompositionTemplate:
        if not _SAFE_NAME.fullmatch(name):
            raise ValueError("template name is invalid")
        path = self.root / f"{name}.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("template file is missing or unsafe")
        return template_from_json(path.read_text(encoding="utf-8"))
