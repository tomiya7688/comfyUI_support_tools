"""Move known third-party applications under external/ without moving their data roots."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


APP_NAMES = (
    "ComfyUI",
    "stable-diffusion-webui",
    "pixai_tagger",
    "taggui",
    "wd14-tagger-standalone",
    "CLIP",
)
PRESERVED_CHILDREN = {
    "ComfyUI": ("models", "output"),
    "stable-diffusion-webui": ("models", "outputs"),
}
PATH_KEYS = ("a1111_dir", "comfyui_dir", "pixai_tagger_dir", "taggui_dir")


# {
#   責務: [
#     MigrationError: user dataを危険にさらさず続行できないmigration failureを表す
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [],
#   引数: [],
#   戻り値: [
#     MigrationError: instance of this class,
#   ],
# }
class MigrationError(RuntimeError):
    """Raised when the migration cannot proceed without risking user data."""


# {
#   責務: [
#     MigrationPlan: application roots、move/link operations、config rewrite planを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     moves: list[tuple[Path, Path]] field stored by this declaration,
#     links: list[tuple[Path, Path]] field stored by this declaration,
#     app_roots: list[tuple[Path, Path]] field stored by this declaration,
#     config_path: Path | None field stored by this declaration,
#     config: dict | None field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     MigrationPlan: instance of this class,
#   ],
# }
@dataclass
class MigrationPlan:
    moves: list[tuple[Path, Path]]
    links: list[tuple[Path, Path]]
    app_roots: list[tuple[Path, Path]]
    config_path: Path | None
    config: dict | None


# {
#   責務: [
#     _is_reparse_point: filesystem metadataからsymlink/junction reparse pointを判定する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path: 検査または変換するfile path (Path),
#   ],
#   戻り値: [
#     result: bool as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


# {
#   責務: [
#     _same_or_child: path textがsource rootそのものか配下か判定する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path_text: untrusted path text from config (str),
#     source: legacy path root (Path),
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: bool as described by the annotated return type,
#   ],
# }
def _same_or_child(path_text: str, source: Path, root: Path) -> bool:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate.resolve(strict=False).relative_to(source.resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


# {
#   責務: [
#     _remap_path: config path referenceをlegacy rootからnew rootへremapする
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path_text: untrusted path text from config (str),
#     source: legacy path root (Path),
#     destination: new path root (Path),
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: str as described by the annotated return type,
#   ],
# }
def _remap_path(path_text: str, source: Path, destination: Path, root: Path) -> str:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    relative = candidate.resolve(strict=False).relative_to(source.resolve(strict=False))
    return str(destination / relative)


# {
#   責務: [
#     _config_path: user config directory内のsupported config fileを解決する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: Path | None as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def _config_path(root: Path) -> Path | None:
    candidates = (
        root / "user_data" / "input" / "config" / "common" / "paths.json",
        root / "user_data" / "paths.json",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


# {
#   責務: [
#     _load_and_remap_config: config JSONを読み込み、known application referencesをremapする
#   ],
#   処理: [
#     1: source/config/metadataを読み込んで解析する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#     app_roots: application source/destination root mapping (list[tuple[Path, Path]]),
#   ],
#   戻り値: [
#     result: tuple[Path | None, dict | None] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
#   エラー: [
#     MigrationError: invalid input, unsafe path, or command failure,
#   ],
# }
def _load_and_remap_config(root: Path, app_roots: list[tuple[Path, Path]]) -> tuple[Path | None, dict | None]:
    config_path = _config_path(root)
    if config_path is None:
        return None, None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MigrationError(f"設定JSONを読み込めません。何も変更していません: {config_path}: {exc}") from exc
    if not isinstance(config, dict):
        raise MigrationError(f"設定JSONの形式がオブジェクトではありません: {config_path}")
    for key in PATH_KEYS:
        value = config.get(key)
        if not isinstance(value, str):
            continue
        for source, destination in app_roots:
            if _same_or_child(value, source, root):
                config[key] = _remap_path(value, source, destination, root)
                break
    return config_path, config


# {
#   責務: [
#     build_plan: legacy paths.jsonとexternal model treeからrepair planを構築する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: 対象 declarations/filesystem entriesを走査する,
#     3: validated resultをcallerへ返す,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: MigrationPlan as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
#   エラー: [
#     MigrationError: invalid input, unsafe path, or command failure,
#   ],
# }
def build_plan(root: Path) -> MigrationPlan:
    root = root.resolve()
    external = root / "external"
    moves: list[tuple[Path, Path]] = []
    links: list[tuple[Path, Path]] = []
    app_roots: list[tuple[Path, Path]] = []
    for name in APP_NAMES:
        source = root / name
        if not source.exists():
            continue
        if not source.is_dir() or _is_reparse_point(source):
            raise MigrationError(f"移動対象が通常のフォルダではありません: {source}")
        destination = external / name
        if destination.exists():
            raise MigrationError(f"移動先が既に存在します。何も変更していません: {destination}")
        app_roots.append((source, destination))
        preserved = {child.casefold() for child in PRESERVED_CHILDREN.get(name, ())}
        for child in source.iterdir():
            if child.name.casefold() in preserved:
                links.append((destination / child.name, child))
            else:
                moves.append((child, destination / child.name))

    for link, _target in links:
        if link.exists() or link.is_symlink():
            raise MigrationError(f"データ参照先が既に存在します。何も変更していません: {link}")
    config_path, config = _load_and_remap_config(root, app_roots)
    return MigrationPlan(moves, links, app_roots, config_path, config)


# {
#   責務: [
#     _create_directory_link: platform-supported directory linkを作成してresultを検証する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: 計画したfilesystem output/updateを適用する,
#     3: validated resultをcallerへ返す,
#   ],
#   引数: [
#     link: link path (Path),
#     target: resolved target path (Path),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     指定されたfilesystem pathsを作成、更新、移動、置換、または削除する,
#     external processを起動し、結果を取得する,
#   ],
#   エラー: [
#     OSError: invalid input, unsafe path, or command failure,
#   ],
# }
def _create_directory_link(link: Path, target: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise OSError(result.stderr.strip() or result.stdout.strip() or "junction作成に失敗しました")
    else:
        os.symlink(target, link, target_is_directory=True)


# {
#   責務: [
#     _remove_directory_link: directory symlink/junctionを安全に削除する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: 計画したfilesystem output/updateを適用する,
#     3: validated resultをcallerへ返す,
#   ],
#   引数: [
#     link: link path (Path),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     指定されたfilesystem pathsを作成、更新、移動、置換、または削除する,
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def _remove_directory_link(link: Path) -> None:
    if link.is_symlink() or _is_reparse_point(link):
        if link.is_dir():
            link.rmdir()
        else:
            link.unlink()


# {
#   責務: [
#     _write_config_atomically: JSON configをtemporary file経由でatomic replaceする
#   ],
#   処理: [
#     1: 計画したfilesystem output/updateを適用する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path: 検査または変換するfile path (Path),
#     config: parsed config mapping (dict),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     指定されたfilesystem pathsを作成、更新、移動、置換、または削除する,
#   ],
# }
def _write_config_atomically(path: Path, config: dict) -> None:
    handle, temporary_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as output:
            json.dump(config, output, ensure_ascii=False, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


# {
#   責務: [
#     _safe_print: terminal encodingで表示できるstatus messageを出力する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     message: status/error message (str),
#     stream: output text stream (unspecified),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     CLI status、finding、またはerrorを標準出力へ表示する,
#   ],
# }
def _safe_print(message: str, stream=None) -> None:
    stream = stream or sys.stdout
    try:
        print(message, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        safe_message = message.encode(encoding, errors="backslashreplace").decode(encoding)
        print(safe_message, file=stream)


# {
#   責務: [
#     _apply_plan: planned moves/links/config rewriteを実行し、failure時にrollbackする
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: 対象 declarations/filesystem entriesを走査する,
#     3: 計画したfilesystem output/updateを適用する,
#   ],
#   引数: [
#     plan: validated filesystem operation plan (MigrationPlan),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     指定されたfilesystem pathsを作成、更新、移動、置換、または削除する,
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
#   エラー: [
#     MigrationError: invalid input, unsafe path, or command failure,
#   ],
# }
def _apply_plan(plan: MigrationPlan) -> None:
    moved: list[tuple[Path, Path]] = []
    created_links: list[Path] = []
    try:
        for _source, app_root in plan.app_roots:
            app_root.mkdir(parents=True, exist_ok=False)
        for source, destination in plan.moves:
            shutil.move(str(source), str(destination))
            moved.append((source, destination))
        for link, target in plan.links:
            _create_directory_link(link, target)
            created_links.append(link)
        for source, _destination in plan.app_roots:
            if source.exists() and not any(source.iterdir()):
                source.rmdir()
        if plan.config_path is not None and plan.config is not None:
            _write_config_atomically(plan.config_path, plan.config)
    except Exception as exc:
        rollback_errors = []
        for link in reversed(created_links):
            try:
                _remove_directory_link(link)
            except OSError as rollback_exc:
                rollback_errors.append(f"リンク {link}: {rollback_exc}")
        for source, destination in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            except OSError as rollback_exc:
                rollback_errors.append(f"{destination} -> {source}: {rollback_exc}")
        for _source, app_root in reversed(plan.app_roots):
            try:
                if app_root.exists() and not any(app_root.iterdir()):
                    app_root.rmdir()
            except OSError as rollback_exc:
                rollback_errors.append(f"空フォルダ {app_root}: {rollback_exc}")
        details = f"処理に失敗したため可能な範囲で元へ戻しました: {exc}"
        if rollback_errors:
            details += "。自動復旧できなかったもの: " + "; ".join(rollback_errors)
        raise MigrationError(details) from exc


# {
#   責務: [
#     migrate: dry-run planを表示し、apply flag時のみmigrationを実施する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#     apply: apply filesystem modifications instead of dry-run (bool),
#   ],
#   戻り値: [
#     result: MigrationPlan as described by the annotated return type,
#   ],
# }
def migrate(root: Path, apply: bool = False) -> MigrationPlan:
    plan = build_plan(root)
    for source, destination in plan.app_roots:
        _safe_print(f"外部アプリ: {source} -> {destination}")
    for link, target in plan.links:
        _safe_print(f"データは元の場所に保持: {link} => {target}")
    if plan.config_path is not None:
        _safe_print(f"設定参照を更新: {plan.config_path}")
    if not apply:
        _safe_print("確認のみです。実際に移動するには --apply を指定してください。")
        return plan
    _apply_plan(plan)
    return plan


# {
#   責務: [
#     main: 外部application migrationをpreviewし、--apply指定時にmove/link/config更新を実行する
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--root, --apply),
#     2: 外部application migrationをpreviewし、--apply指定時にmove/link/config更新を実行する,
#     3: resultとexit statusを返す,
#   ],
#   引数: [
#     argv: command-line argument vector (list[str] | None),
#   ],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     filesystem migrationとpaths.json更新は--apply指定時のみ実行する,
#     preview、結果、またはerrorを標準出力または標準errorへ表示する,
#   ],
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="既知の外部アプリだけを external/ へ移します")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--apply", action="store_true", help="事前確認後にフォルダと paths.json を更新する")
    args = parser.parse_args(argv)
    try:
        migrate(args.root, apply=args.apply)
    except MigrationError as exc:
        _safe_print(f"エラー: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
