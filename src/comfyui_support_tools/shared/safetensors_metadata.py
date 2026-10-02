"""Read the small JSON header from a safetensors model file."""

from __future__ import annotations

import json
import struct
from pathlib import Path


_MAX_HEADER_BYTES = 64 * 1024 * 1024


class SafetensorsMetadataError(ValueError):
    """Raised when a safetensors header is missing, malformed, or too large."""


def _read_header(path: str | Path) -> dict:
    """Read only the bounded JSON header, never the tensor payload."""
    model_path = Path(path)
    try:
        with model_path.open("rb") as model_file:
            length_bytes = model_file.read(8)
            if len(length_bytes) != 8:
                raise SafetensorsMetadataError("file is shorter than the 8-byte header length")
            header_length = struct.unpack("<Q", length_bytes)[0]
            if header_length == 0:
                raise SafetensorsMetadataError("header length is zero")
            if header_length > _MAX_HEADER_BYTES:
                raise SafetensorsMetadataError(
                    f"header length {header_length} exceeds the {_MAX_HEADER_BYTES}-byte limit"
                )
            header_bytes = model_file.read(header_length)
    except OSError as exc:
        raise SafetensorsMetadataError(f"cannot read {model_path}: {exc}") from exc

    if len(header_bytes) != header_length:
        raise SafetensorsMetadataError("file ended before the complete header was read")
    try:
        header = json.loads(header_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SafetensorsMetadataError(f"header is not valid JSON: {exc}") from exc
    if not isinstance(header, dict):
        raise SafetensorsMetadataError("header JSON must be an object")
    return header


def _text_metadata(header: dict) -> dict[str, str]:
    metadata = header.get("__metadata__", {})
    if not isinstance(metadata, dict):
        raise SafetensorsMetadataError("__metadata__ must be an object")
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items()):
        raise SafetensorsMetadataError("safetensors metadata keys and values must be strings")
    return metadata


def read_safetensors_metadata(path: str | Path) -> dict[str, str]:
    """Read text metadata without loading tensor weights into memory."""
    return _text_metadata(_read_header(path))


def read_safetensors_evidence(path: str | Path) -> tuple[dict[str, str], dict[str, tuple[int, ...]]]:
    """Read metadata and shape descriptors with a single bounded header read."""
    header = _read_header(path)
    metadata = _text_metadata(header)
    shapes = {}
    for name, descriptor in header.items():
        if name == "__metadata__":
            continue
        shape = descriptor.get("shape") if isinstance(descriptor, dict) else None
        if not isinstance(shape, list) or any(type(dimension) is not int or dimension < 0 for dimension in shape):
            raise SafetensorsMetadataError(f"invalid tensor shape descriptor: {name}")
        shapes[name] = tuple(shape)
    return metadata, shapes
