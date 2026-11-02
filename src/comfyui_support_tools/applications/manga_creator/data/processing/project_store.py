"""Versioned safe JSON persistence for editable manga projects."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from comfyui_support_tools.shared.contracts.manga_creator import MangaProject

MAX_PROJECT_BYTES = 64 * 1024 * 1024
MAX_PROJECT_ITEMS = 5000


# {
# 責務: [_encode: convert a project contract into JSON values]
# 処理: [recursively serialize dataclasses, enums and tuples]
# 引数: [value: project contract value]
# 戻り値: [object: JSON-compatible data]
# }
def _encode(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    return value


# {
# 責務: [_unique_object: reject duplicate JSON object keys]
# 処理: [build a mapping only when each key appears once]
# 引数: [pairs: parser key/value pairs]
# 戻り値: [dict[str, Any]: unique JSON object]
# }
def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate project field: {key}")
        result[key] = value
    return result


# {
# 責務: [_decode: validate and construct a typed project value]
# 処理: [recursively decode dataclasses, enums, optional values and bounded tuples]
# 引数: [annotation: target contract type, value: untrusted JSON data, path: field path]
# 戻り値: [object: validated contract value]
# }
def _decode(annotation: Any, value: object, path: str) -> object:
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is tuple:
        if not isinstance(value, list) or len(value) > MAX_PROJECT_ITEMS:
            raise ValueError(f"{path} must be an array with at most {MAX_PROJECT_ITEMS} entries")
        item_type = arguments[0] if arguments else Any
        if len(arguments) > 1 and arguments[1] is not Ellipsis:
            if len(value) != len(arguments):
                raise ValueError(f"{path} has an invalid tuple length")
            return tuple(
                _decode(kind, item, f"{path}[{index}]")
                for index, (kind, item) in enumerate(zip(arguments, value, strict=True))
            )
        return tuple(
            _decode(item_type, item, f"{path}[{index}]") for index, item in enumerate(value)
        )
    if origin is not None and type(None) in arguments:
        if value is None:
            return None
        nested_type = next(kind for kind in arguments if kind is not type(None))
        return _decode(nested_type, value, path)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        try:
            return annotation(value)
        except ValueError as error:
            raise ValueError(f"{path} has an unknown enum value") from error
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        definitions = {field.name: field for field in fields(annotation)}
        if set(value) != set(definitions):
            raise ValueError(f"{path} has missing or unsupported fields")
        hints = get_type_hints(annotation)
        decoded = {
            name: _decode(hints[name], item, f"{path}.{name}") for name, item in value.items()
        }
        try:
            return annotation(**decoded)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{path} violates the project schema: {error}") from error
    if annotation is Any:
        return value
    if annotation is bool:
        if not isinstance(value, bool):
            raise ValueError(f"{path} must be a boolean")
        return value
    if annotation is int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{path} must be an integer")
        return value
    if annotation is float:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError(f"{path} must be a finite number")
        return float(value)
    if annotation is str:
        if not isinstance(value, str):
            raise ValueError(f"{path} must be a string")
        return value
    if value is None or isinstance(value, annotation):
        return value
    raise ValueError(f"{path} has an unsupported value type")


# {
# 責務: [project_to_json: serialize a bounded versioned manga project]
# 処理: [encode project data as deterministic UTF-8 JSON]
# 引数: [project: validated editable manga project]
# 戻り値: [str: JSON document]
# }
def project_to_json(project: MangaProject) -> str:
    return json.dumps(_encode(project), ensure_ascii=False, indent=2, allow_nan=False) + "\n"


# {
# 責務: [project_from_json: parse and validate an untrusted manga project]
# 処理: [reject oversized, duplicate-key, non-finite or schema-incompatible documents]
# 引数: [document: project JSON text]
# 戻り値: [MangaProject: validated editable project]
# }
def project_from_json(document: str) -> MangaProject:
    if not isinstance(document, str) or len(document.encode("utf-8")) > MAX_PROJECT_BYTES:
        raise ValueError("manga project exceeds the 64 MiB limit")

    # {
    #   責務: [reject_constant: reject JavaScript-style non-finite JSON numbers]
    #   処理: [raise ValueError for NaN and Infinity tokens]
    #   引数: [constant: unsupported JSON numeric token]
    #   戻り値: []
    # }
    def reject_constant(constant: str) -> None:
        raise ValueError(f"non-standard JSON number {constant} is not supported")

    try:
        raw = json.loads(document, parse_constant=reject_constant, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError("manga project JSON is malformed") from error
    result = _decode(MangaProject, raw, "project")
    if not isinstance(result, MangaProject):
        raise ValueError("manga project root must be an object")
    return result


# {
# 責務: [MangaProjectStore: load and atomically save editable project state]
# フィールド: [no mutable state]
# 処理: [persist project JSON safely so generation can resume after restart]
# }
class MangaProjectStore:
    # {
    # 責務: [load: read one bounded manga project]
    # 処理: [reject symlinks and oversize input before strict schema decoding]
    # 引数: [path: project JSON path]
    # 戻り値: [MangaProject: validated project]
    # }
    def load(self, path: str | Path) -> MangaProject:
        source = Path(path)
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_PROJECT_BYTES:
            raise ValueError("project file is missing or exceeds 64 MiB")
        return project_from_json(source.read_text(encoding="utf-8"))

    # {
    # 責務: [save: atomically update one project JSON file]
    # 処理: [write and fsync a same-directory temporary file, then replace the destination]
    # 引数: [project: validated state, path: destination project file]
    # 戻り値: [Path: saved project path]
    # }
    def save(self, project: MangaProject, path: str | Path) -> Path:
        destination = Path(path).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_symlink():
            raise ValueError("project destination cannot be a symbolic link")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(project_to_json(project))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return destination
