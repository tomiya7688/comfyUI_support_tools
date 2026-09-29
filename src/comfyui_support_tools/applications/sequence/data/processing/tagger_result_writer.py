"""Write explicit Tagger text and metadata sidecar files."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


class TaggerResultWriter:
    """Atomically persist user-selected Tagger result sidecars."""

    @staticmethod
    def validate_path(value: Any, name: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty absolute file path")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError(f"{name} must be an absolute file path")
        if path.is_symlink() or path.exists() and not path.is_file():
            raise ValueError(f"{name} must be a regular file path, not a symbolic link or directory")
        return path

    def write_text(self, path: Path, value: str) -> Path:
        return self._write(path, value.rstrip("\r\n") + "\n")

    def write_metadata(self, path: Path, value: Mapping[str, Any]) -> Path:
        serialized = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        return self._write(path, serialized)

    @staticmethod
    def _write(path: Path, value: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(value)
            os.replace(temporary_name, path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
        return path
