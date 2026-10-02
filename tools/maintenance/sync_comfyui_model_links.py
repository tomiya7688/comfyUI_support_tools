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


class ModelLinkError(RuntimeError):
    """Raised when a model link cannot be safely inspected or replaced."""


@dataclass(frozen=True)
class LinkRepair:
    link: Path
    old_target: Path
    new_target: Path


@dataclass
class RepairPlan:
    repairs: list[LinkRepair]
    skipped: list[str]


def _safe_print(message: str, stream=None) -> None:
    stream = stream or sys.stdout
    try:
        print(message, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        safe_message = message.encode(encoding, errors="backslashreplace").decode(encoding)
        print(safe_message, file=stream)


def _absolute_path(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve(strict=False)


def _strip_windows_namespace(value: str) -> str:
    if value.startswith("\\\\?\\"):
        return value[4:]
    if value.startswith("\\??\\"):
        return value[4:]
    return value


def _read_link_target(link: Path) -> Path:
    try:
        target_text = _strip_windows_namespace(os.readlink(link))
    except OSError as exc:
        raise ModelLinkError(f"Cannot read model link {link}: {exc}") from exc
    target = Path(target_text)
    if not target.is_absolute():
        target = link.parent / target
    return target.resolve(strict=False)


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _relative_to_legacy_root(target: Path, legacy_root: Path) -> Path | None:
    try:
        relative = os.path.relpath(str(target), str(legacy_root))
    except ValueError:
        return None
    if relative in {".", ".."} or relative.startswith(f"..{os.sep}"):
        return None
    return Path(relative)


def _model_directory_index(models_root: Path) -> dict[str, Path]:
    if not models_root.is_dir():
        raise ModelLinkError(f"Configured shared models directory does not exist: {models_root}")
    return {
        child.name.casefold(): child
        for child in models_root.iterdir()
        if child.is_dir()
    }


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


def _load_paths(config_path: Path) -> dict[str, str]:
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelLinkError(f"Cannot read paths configuration {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelLinkError(f"Path configuration must be a JSON object: {config_path}")
    return data


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


def _remove_directory_link(link: Path) -> None:
    if os.name == "nt" and _is_reparse_point(link):
        os.rmdir(link)
    elif link.is_dir():
        os.rmdir(link)
    else:
        link.unlink()


def _validate_plan(plan: RepairPlan) -> None:
    for repair in plan.repairs:
        if not _is_reparse_point(repair.link):
            raise ModelLinkError(f"Link changed after planning; refusing to replace: {repair.link}")
        current_target = _read_link_target(repair.link)
        if current_target != repair.old_target or current_target.exists():
            raise ModelLinkError(f"Link target changed after planning; refusing to replace: {repair.link}")
        if not repair.new_target.is_dir():
            raise ModelLinkError(f"Shared model directory disappeared: {repair.new_target}")


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
