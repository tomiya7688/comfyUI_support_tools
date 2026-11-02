"""Read the small JSON header from a safetensors model file."""

from __future__ import annotations

import json
import struct
from pathlib import Path


_MAX_HEADER_BYTES = 64 * 1024 * 1024


# {
# 責務: [SafetensorsMetadataError: safetensors headerの読み取りまたはvalidation失敗を表す]
# フィールド: [ValueError message]
# }
class SafetensorsMetadataError(ValueError):
    """Raised when a safetensors header is missing, malformed, or too large."""


# {
#   責務: [_read_header: 8-byte lengthを使い、上限付きでJSON headerだけを読む]
#   処理: [header長/完全性/JSON objectを検証し、tensor payloadは読み込まない]
#   引数: [path: safetensors file path]
#   戻り値: [header: parsed JSON object]
#   エラー: [SafetensorsMetadataError: file I/O、header長、JSON形式が不正]
# }
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


# {
#   責務: [_text_metadata: headerの__metadata__をstring-to-string mappingとして検証する]
#   処理: [未指定metadataは空mappingとし、container/key/value型を確認する]
#   引数: [header: parsed safetensors header]
#   戻り値: [metadata: text metadata mapping]
#   エラー: [SafetensorsMetadataError: metadata containerまたは要素型が不正]
# }
def _text_metadata(header: dict) -> dict[str, str]:
    metadata = header.get("__metadata__", {})
    if not isinstance(metadata, dict):
        raise SafetensorsMetadataError("__metadata__ must be an object")
    if any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in metadata.items()
    ):
        raise SafetensorsMetadataError("safetensors metadata keys and values must be strings")
    return metadata


# {
#   責務: [read_safetensors_metadata: tensor dataを展開せず文字列metadataだけを読む]
#   処理: [_read_headerでheaderを読み、__metadata__を検証して返す]
#   引数: [path: safetensors file path]
#   戻り値: [metadata: key/valueが文字列のmapping]
#   エラー: [SafetensorsMetadataError: headerまたはmetadataが不正]
# }
def read_safetensors_metadata(path: str | Path) -> dict[str, str]:
    """Read text metadata without loading tensor weights into memory."""
    return _text_metadata(_read_header(path))


# {
#   責務: [read_safetensors_evidence: 1回のheader readからmetadataとtensor shapeを抽出する]
#   処理: [metadataを検証し、tensorごとのshapeを非負整数tupleへ変換する]
#   引数: [path: safetensors file path]
#   戻り値: [metadataとtensor name-to-shape mappingのtuple]
#   エラー: [SafetensorsMetadataError: header/metadata/shape descriptorが不正]
# }
def read_safetensors_evidence(
    path: str | Path,
) -> tuple[dict[str, str], dict[str, tuple[int, ...]]]:
    """Read metadata and shape descriptors with a single bounded header read."""
    header = _read_header(path)
    metadata = _text_metadata(header)
    shapes = {}
    for name, descriptor in header.items():
        if name == "__metadata__":
            continue
        shape = descriptor.get("shape") if isinstance(descriptor, dict) else None
        if not isinstance(shape, list) or any(
            type(dimension) is not int or dimension < 0 for dimension in shape
        ):
            raise SafetensorsMetadataError(f"invalid tensor shape descriptor: {name}")
        shapes[name] = tuple(shape)
    return metadata, shapes
