"""Bounded JSON persistence for Pixiv query presets."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .contracts import PixivQueryPreset, PixivRateLimitProfile


# {
# 責務: [PixivQueryPresetStore: persist reusable source queries without credentials]
# フィールド: [preset JSON file]
# }
class PixivQueryPresetStore:
    # {
    # 責務: [__init__: set preset storage file]
    # 処理: [do not create the file until a preset is saved]
    # 引数: [path: JSON file]
    # 戻り値: [None: store ready]
    # }
    def __init__(self, path):
        self.path = Path(path)

    # {
    # 責務: [list: return saved preset names]
    # 処理: [read a bounded validated JSON document]
    # 引数: [None: reads configured store]
    # 戻り値: [tuple[str, ...]: sorted names]
    # }
    def list(self):
        return tuple(sorted(self._read()))

    # {
    # 責務: [get: load one saved preset by name]
    # 処理: [restore typed query and tuple fields]
    # 引数: [name: stored preset name]
    # 戻り値: [PixivQueryPreset: restored preset]
    # }
    def get(self, name):
        try:
            row = self._read()[name]
        except KeyError:
            raise KeyError(f"Pixiv query preset not found: {name}") from None
        row["work_ids"] = tuple(row.get("work_ids", ()))
        row["filters"] = tuple(
            (key, _restore_sequence(value)) for key, value in row.get("filters", ())
        )
        rate_limit = row.get("rate_limit")
        if isinstance(rate_limit, dict):
            row["rate_limit"] = PixivRateLimitProfile(**rate_limit)
        return PixivQueryPreset(**row)

    # {
    # 責務: [save: create or explicitly replace a named preset]
    # 処理: [persist atomically and never serialize credentials]
    # 引数: [preset: user query, overwrite: permit same-name replacement]
    # 戻り値: [None: preset saved]
    # }
    def save(self, preset, overwrite=False):
        if not isinstance(preset, PixivQueryPreset) or not preset.name.strip():
            raise ValueError("a named Pixiv query preset is required")
        rows = self._read()
        if preset.name in rows and not overwrite:
            raise FileExistsError(f"Pixiv query preset already exists: {preset.name}")
        rows[preset.name] = asdict(preset)
        if len(rows) > 1000:
            raise ValueError("at most 1000 Pixiv query presets may be stored")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError("preset store cannot be a symlink")
        payload = (json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, prefix=f".{self.path.name}.", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    # {
    # 責務: [_read: validate and load bounded named preset mappings]
    # 処理: [reject symlinks, oversized files, malformed records, and duplicate names]
    # 引数: [None: reads configured store]
    # 戻り値: [dict[str, dict]: saved presets]
    # }
    def _read(self):
        if self.path.is_symlink() or not self.path.is_file():
            return {}
        if self.path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Pixiv query preset file exceeds 16 MiB")
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ValueError("Pixiv query preset file is invalid") from None
        if not isinstance(rows, dict) or len(rows) > 1000:
            raise ValueError("Pixiv query preset document is invalid")
        return rows


# {
# 責務: [_restore_sequence: reconstruct immutable tuple filter values after JSON loading]
# 処理: [convert nested arrays while preserving scalar JSON types]
# 引数: [value: decoded JSON value]
# 戻り値: [object: recursively restored value]
# }
def _restore_sequence(value):
    if isinstance(value, list):
        return tuple(_restore_sequence(item) for item in value)
    if isinstance(value, dict):
        return {key: _restore_sequence(item) for key, item in value.items()}
    return value
