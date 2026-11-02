"""Repair broken ComfyUI model junctions using the configured shared model root."""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [
#     ModelLinkError: model linkを安全に検査・置換できないfailureを表す
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [],
#   引数: [],
#   戻り値: [
#     ModelLinkError: instance of this class,
#   ],
# }
class ModelLinkError(RuntimeError):
    """Raised when a model link cannot be safely inspected or replaced."""


# {
#   責務: [
#     LinkRepair: 一つのlegacy model linkのtarget/repair actionを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     link: Path field stored by this declaration,
#     old_target: Path field stored by this declaration,
#     new_target: Path field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     LinkRepair: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class LinkRepair:
    link: Path
    old_target: Path
    new_target: Path


# {
#   責務: [
#     RepairPlan: model link repairsとwarningsを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     repairs: list[LinkRepair] field stored by this declaration,
#     skipped: list[str] field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     RepairPlan: instance of this class,
#   ],
# }
@dataclass
class RepairPlan:
    repairs: list[LinkRepair]
    skipped: list[str]


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
#     _absolute_path: user pathをroot基準でabsolute normalized pathへ変換する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     value: input value (str),
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: Path as described by the annotated return type,
#   ],
# }
def _absolute_path(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve(strict=False)


# {
#   責務: [
#     _strip_windows_namespace: Windows extended-length path prefixを除去する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     value: input value (str),
#   ],
#   戻り値: [
#     result: str as described by the annotated return type,
#   ],
# }
def _strip_windows_namespace(value: str) -> str:
    if value.startswith("\\\\?\\"):
        return value[4:]
    if value.startswith("\\??\\"):
        return value[4:]
    return value


# {
#   責務: [
#     _read_link_target: symlink/junction targetを読み取り、safe absolute pathを返す
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     link: link path (Path),
#   ],
#   戻り値: [
#     result: Path as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
#   エラー: [
#     ModelLinkError: invalid input, unsafe path, or command failure,
#   ],
# }
def _read_link_target(link: Path) -> Path:
    try:
        target_text = _strip_windows_namespace(os.readlink(link))
    except OSError as exc:
        raise ModelLinkError(f"Cannot read model link {link}: {exc}") from exc
    target = Path(target_text)
    if not target.is_absolute():
        target = link.parent / target
    return target.resolve(strict=False)


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
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return path.is_symlink() or bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


# {
#   責務: [
#     _relative_to_legacy_root: targetがlegacy root内にある場合のrelative pathを返す
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     target: resolved target path (Path),
#     legacy_root: legacy ComfyUI root (Path),
#   ],
#   戻り値: [
#     result: Path | None as described by the annotated return type,
#   ],
# }
def _relative_to_legacy_root(target: Path, legacy_root: Path) -> Path | None:
    try:
        relative = os.path.relpath(str(target), str(legacy_root))
    except ValueError:
        return None
    if relative in {".", ".."} or relative.startswith(f"..{os.sep}"):
        return None
    return Path(relative)


# {
#   責務: [
#     _model_directory_index: ComfyUI model subdirectoriesをcase-insensitive indexにする
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: 対象 declarations/filesystem entriesを走査する,
#     3: validated resultをcallerへ返す,
#   ],
#   引数: [
#     models_root: ComfyUI model directory (Path),
#   ],
#   戻り値: [
#     result: dict[str, Path] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
#   エラー: [
#     ModelLinkError: invalid input, unsafe path, or command failure,
#   ],
# }
def _model_directory_index(models_root: Path) -> dict[str, Path]:
    if not models_root.is_dir():
        raise ModelLinkError(f"Configured shared models directory does not exist: {models_root}")
    return {
        child.name.casefold(): child
        for child in models_root.iterdir()
        if child.is_dir()
    }


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
#     paths: paths value used by build_plan (dict[str, str]),
#   ],
#   戻り値: [
#     result: RepairPlan as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
#   エラー: [
#     ModelLinkError: invalid input, unsafe path, or command failure,
#   ],
# }
def build_plan(paths: dict[str, str]) -> RepairPlan:
    required = ("sd_root", "comfyui_dir")
    missing = [key for key in required if not isinstance(paths.get(key), str) or not paths[key].strip()]
    if missing:
        raise ModelLinkError(f"Missing path configuration: {', '.join(missing)}")
    models_value = paths.get("models_root") or paths.get("input_models")
    if not isinstance(models_value, str) or not models_value.strip():
        raise ModelLinkError("Missing shared model root in paths.json (models_root/input_models)")

    root = _absolute_path(paths["sd_root"], Path.cwd())
    legacy_root = (root / "models").resolve(strict=False)
    models_root = _absolute_path(models_value, root)
    comfy_models = _absolute_path(paths["comfyui_dir"], root) / "models"
    if not comfy_models.is_dir():
        raise ModelLinkError(f"ComfyUI models directory does not exist: {comfy_models}")

    model_directories = _model_directory_index(models_root)
    repairs: list[LinkRepair] = []
    skipped: list[str] = []
    for link in sorted(comfy_models.iterdir(), key=lambda item: item.name.casefold()):
        if not _is_reparse_point(link):
            continue
        old_target = _read_link_target(link)
        if old_target.exists():
            continue
        relative = _relative_to_legacy_root(old_target, legacy_root)
        if relative is None or len(relative.parts) != 1:
            continue
        new_target = model_directories.get(relative.name.casefold())
        if new_target is None:
            skipped.append(f"{link} -> {old_target} (no matching folder in {models_root})")
            continue
        repairs.append(LinkRepair(link=link, old_target=old_target, new_target=new_target))
    return RepairPlan(repairs=repairs, skipped=skipped)


# {
#   責務: [
#     _load_paths: paths.json mappingを読み込み、object schemaを検証する
#   ],
#   処理: [
#     1: source/config/metadataを読み込んで解析する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     config_path: paths.json/config file path (Path),
#   ],
#   戻り値: [
#     result: dict[str, str] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
#   エラー: [
#     ModelLinkError: invalid input, unsafe path, or command failure,
#   ],
# }
def _load_paths(config_path: Path) -> dict[str, str]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelLinkError(f"Cannot read paths configuration {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelLinkError(f"Path configuration must be a JSON object: {config_path}")
    return data


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
            raise OSError(result.stderr.strip() or result.stdout.strip() or "Could not create junction")
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
    if os.name == "nt" and _is_reparse_point(link):
        os.rmdir(link)
    elif link.is_dir():
        os.rmdir(link)
    else:
        link.unlink()


# {
#   責務: [
#     _validate_plan: apply前に各existing/new link targetとoperationを再検証する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     plan: validated filesystem operation plan (RepairPlan),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
#   エラー: [
#     ModelLinkError: invalid input, unsafe path, or command failure,
#   ],
# }
def _validate_plan(plan: RepairPlan) -> None:
    for repair in plan.repairs:
        if not _is_reparse_point(repair.link):
            raise ModelLinkError(f"Link changed after planning; refusing to replace: {repair.link}")
        current_target = _read_link_target(repair.link)
        if current_target != repair.old_target or current_target.exists():
            raise ModelLinkError(f"Link target changed after planning; refusing to replace: {repair.link}")
        if not repair.new_target.is_dir():
            raise ModelLinkError(f"Shared model directory disappeared: {repair.new_target}")


# {
#   責務: [
#     apply_plan: repair planを適用し、partial failure時にprevious linksをrollbackする
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     plan: validated filesystem operation plan (RepairPlan),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   エラー: [
#     ModelLinkError: invalid input, unsafe path, or command failure,
#   ],
# }
def apply_plan(plan: RepairPlan) -> None:
    _validate_plan(plan)
    replaced: list[LinkRepair] = []
    try:
        for repair in plan.repairs:
            _remove_directory_link(repair.link)
            try:
                _create_directory_link(repair.link, repair.new_target)
            except Exception:
                _create_directory_link(repair.link, repair.old_target)
                raise
            replaced.append(repair)
    except Exception as exc:
        rollback_errors = []
        for repair in reversed(replaced):
            try:
                _remove_directory_link(repair.link)
                _create_directory_link(repair.link, repair.old_target)
            except OSError as rollback_exc:
                rollback_errors.append(f"{repair.link}: {rollback_exc}")
        details = f"Could not complete model link repair: {exc}"
        if rollback_errors:
            details += "; rollback failures: " + "; ".join(rollback_errors)
        raise ModelLinkError(details) from exc


# {
#   責務: [
#     repair: dry-run repair planを表示し、apply時だけComfyUI model linksを変更する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     config_path: paths.json/config file path (Path),
#     apply: apply filesystem modifications instead of dry-run (bool),
#   ],
#   戻り値: [
#     result: RepairPlan as described by the annotated return type,
#   ],
# }
def repair(config_path: Path, apply: bool = False) -> RepairPlan:
    plan = build_plan(_load_paths(config_path))
    for item in plan.repairs:
        _safe_print(f"{item.link} -> {item.new_target}")
    for item in plan.skipped:
        _safe_print(f"Skipped: {item}")
    if not plan.repairs:
        _safe_print("No eligible broken ComfyUI model links found.")
        return plan
    if not apply:
        _safe_print("Preview only. Re-run with --apply to replace only these broken junctions.")
        return plan
    apply_plan(plan)
    return plan


# {
#   責務: [
#     main: ComfyUI shared model linksをpreviewし、--apply指定時にeligible broken linksを修復する
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--config, --apply),
#     2: ComfyUI shared model linksをpreviewし、--apply指定時にeligible broken linksを修復する,
#     3: resultとexit statusを返す,
#   ],
#   引数: [
#     argv: command-line argument vector (list[str] | None),
#   ],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     model directory linksの置換は--apply指定時のみ実行する,
#     preview、結果、またはerrorを標準出力または標準errorへ表示する,
#   ],
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair ComfyUI links to the configured shared model root")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "user_data" / "input" / "config" / "common" / "paths.json",
    )
    parser.add_argument("--apply", action="store_true", help="replace the eligible broken directory links")
    args = parser.parse_args(argv)
    try:
        repair(args.config, apply=args.apply)
    except ModelLinkError as exc:
        _safe_print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
