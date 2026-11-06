from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath


# {
#   責務: [CharacterWildcardFileStore: relative wildcard bundleを指定rootへ安全に保存する]
#   フィールド: [なし]
# }
class CharacterWildcardFileStore:
    # {
    #   責務: [write: wildcard本文一式をUTF-8の個別atomic replaceで保存する]
    #   処理: [相対POSIX pathを検証し, targetごとにtemporary fileから置換する]
    #   引数: [self: file store, wildcard_root: 設定済み保存root, files: 相対pathと本文の対応]
    #   戻り値: [tuple[Path, ...]: 保存したabsolute path]
    #   エラー: [ValueError: root/path/bodyが不正な場合, OSError: 保存できない場合]
    # }
    def write(
        self,
        wildcard_root: Path,
        files: Mapping[str, str],
    ) -> tuple[Path, ...]:
        configured_root = Path(wildcard_root).expanduser()
        if not configured_root.is_absolute():
            raise ValueError("wildcard_rootはabsolute pathで指定してください")
        root = configured_root.resolve()
        if not isinstance(files, Mapping) or not files:
            raise ValueError("wildcard filesを1件以上指定してください")

        targets = self._resolve_targets(root, files)
        written: list[Path] = []
        for target, content in targets:
            self._write_atomically(target, content)
            written.append(target)
        return tuple(written)

    # {
    #   責務: [_resolve_targets: relative pathと本文をroot内のtargetへ解決する]
    #   処理: [absolute, traversal, backslash, duplicate path, non-string bodyを拒否する]
    #   引数: [root: resolved wildcard root, files: relative pathとUTF-8本文]
    #   戻り値: [tuple[tuple[Path, str], ...]: 保存順のtargetと本文]
    #   エラー: [ValueError: root外pathまたは不正なentryがある場合]
    # }
    @staticmethod
    def _resolve_targets(
        root: Path,
        files: Mapping[str, str],
    ) -> tuple[tuple[Path, str], ...]:
        targets: list[tuple[Path, str]] = []
        seen_targets: set[str] = set()
        for relative_name, content in files.items():
            if (
                not isinstance(relative_name, str)
                or not relative_name
                or "\\" in relative_name
                or ":" in relative_name
            ):
                raise ValueError("wildcard pathは相対POSIX pathで指定してください")
            relative_path = PurePosixPath(relative_name)
            if (
                relative_path.is_absolute()
                or not relative_path.parts
                or any(part in {".", ".."} for part in relative_path.parts)
            ):
                raise ValueError("wildcard pathにabsolute pathやparent traversalは使えません")
            if not isinstance(content, str):
                raise ValueError("wildcard本文は文字列で指定してください")

            target = root.joinpath(*relative_path.parts).resolve()
            if target != root and root not in target.parents:
                raise ValueError("wildcard pathはwildcard root内にある必要があります")
            target_key = str(target).casefold()
            if target_key in seen_targets:
                raise ValueError("wildcard bundleに重複target pathがあります")
            seen_targets.add(target_key)
            targets.append((target, content))
        return tuple(targets)

    # {
    #   責務: [_write_atomically: 1つのwildcard fileを同じdirectory内でatomicに置換する]
    #   処理: [temporary fileへUTF-8で書き込み, flush/fsync後にos.replaceする]
    #   引数: [target: 保存先, content: UTF-8本文]
    #   戻り値: []
    #   エラー: [OSError: file作成・書込み・置換に失敗した場合]
    # }
    @staticmethod
    def _write_atomically(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.stem}.",
            suffix=".tmp",
            dir=target.parent,
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, target)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
