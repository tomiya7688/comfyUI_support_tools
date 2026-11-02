"""Write explicit Tagger text and metadata sidecar files."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


# {
# 責務: [TaggerResultWriter: 明示指定されたTagger text/metadata sidecarをatomic保存する]
# フィールド: [stateless helper。instance stateなし]
# }
class TaggerResultWriter:
    """Atomically persist user-selected Tagger result sidecars."""

    # {
    #   責務: [validate_path: sidecar出力先をabsolute regular file pathとして検証する]
    #   処理: [expanduser後に絶対pathを要求し、symlink/directory等を拒否する]
    #   引数: [value: path候補, name: validation error用field名]
    #   戻り値: [Path: 検証済み出力path]
    #   エラー: [ValueError: 空/相対/symlink/regular fileでないpath]
    # }
    @staticmethod
    def validate_path(value: Any, name: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty absolute file path")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError(f"{name} must be an absolute file path")
        if path.is_symlink() or path.exists() and not path.is_file():
            raise ValueError(
                f"{name} must be a regular file path, not a symbolic link or directory"
            )
        return path

    # {
    #   責務: [write_text: text sidecarを末尾改行一つ付きでatomic保存する]
    #   処理: [既存末尾CR/LFを取り除きnewlineを付けて共通writerへ渡す]
    #   引数: [self: writer instance, path: output path, value: text body]
    #   戻り値: [Path: 書込先path]
    #   副作用: [output fileを作成または置換する]
    #   エラー: [OSError: pathを作成/書込できない]
    # }
    def write_text(self, path: Path, value: str) -> Path:
        return self._write(path, value.rstrip("\r\n") + "\n")

    # {
    #   責務: [write_metadata: metadata mappingをNaN禁止/UTF-8 JSONとしてatomic保存する]
    #   処理: [indent付きJSONと末尾改行を作り共通writerへ渡す]
    #   引数: [self: writer instance, path: output path, value: metadata mapping]
    #   戻り値: [Path: 書込先path]
    #   副作用: [output fileを作成または置換する]
    #   エラー: [TypeError/ValueError: dataがJSON serializableでない, OSError: file operation失敗]
    # }
    def write_metadata(self, path: Path, value: Mapping[str, Any]) -> Path:
        serialized = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
        return self._write(path, serialized)

    # {
    #   責務: [_write: same-directory temporary file経由でtextをatomic replaceする]
    #   処理: [parent作成、UTF-8 temp write、os.replaceを行いfailure時tempを消す]
    #   引数: [path: destination, value: complete text content]
    #   戻り値: [Path: destination]
    #   副作用: [directory/fileを作成または置換し、failure時tempを削除する]
    #   エラー: [OSError: filesystem operation失敗]
    # }
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
