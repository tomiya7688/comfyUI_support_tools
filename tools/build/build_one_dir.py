"""Build the Kadoka Tools one-dir distribution with PyInstaller."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_BUILD_TOOL_DIR = str(Path(__file__).resolve().parent)
if _BUILD_TOOL_DIR not in sys.path:
    sys.path.insert(0, _BUILD_TOOL_DIR)
from license_inventory import collect_license_inventory

APP_NAME = "KadokaTools"
EXCLUDED_MODULES = ("torch", "torchvision", "torchaudio")


def executable_path(output: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return output / APP_NAME / f"{APP_NAME}{suffix}"


def _build_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH"):
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    if os.name == "nt":
        system_root = Path(
            environment.get("SystemRoot") or environment.get("WINDIR") or r"C:\Windows"
        )
        allowed_paths = (
            Path(sys.prefix) / "Scripts",
            Path(sys.base_prefix),
            system_root / "System32",
            system_root,
        )
        environment["PATH"] = os.pathsep.join(str(path) for path in allowed_paths)
    return environment


def build(root: Path, output: Path) -> Path:
    work_dir = root / "build" / "pyinstaller"
    work_dir.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--contents-directory",
        ".",
        "--name",
        APP_NAME,
        "--distpath",
        str(output),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
        "--paths",
        str(root / "src"),
    ]
    for module_name in EXCLUDED_MODULES:
        command.extend(("--exclude-module", module_name))
    command.append(str(root / "tabbed_tools_gui.py"))

    subprocess.run(command, cwd=root, env=_build_environment(), check=True)

    distribution_dir = output / APP_NAME
    (distribution_dir / "user_data" / "input" / "config" / "common").mkdir(
        parents=True,
        exist_ok=True,
    )
    executable = executable_path(output)
    if not executable.is_file():
        raise FileNotFoundError(f"PyInstaller output executable was not created: {executable}")
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        source = root / filename
        if not source.is_file():
            raise FileNotFoundError(f"Required license notice was not found: {source}")
        shutil.copy2(source, distribution_dir / filename)
    collect_license_inventory(root, distribution_dir, work_dir / APP_NAME / "COLLECT-00.toc")
    return executable


def run_smoke_test(executable: Path) -> None:
    # Do not accidentally import from the checkout or a user's Python setup.
    executable = executable.resolve()
    environment = os.environ.copy()
    for key in ("PYTHONHOME", "PYTHONPATH"):
        environment.pop(key, None)
    environment["PYTHONNOUSERSITE"] = "1"
    if os.name == "nt":
        system_root = Path(os.environ["SystemRoot"])
        environment["PATH"] = os.pathsep.join((str(system_root / "System32"), str(system_root)))
    with tempfile.TemporaryDirectory(prefix="Kadoka smoke 日本語 ") as cwd:
        for flags in (("--smoke-test",), ("--new-ui", "--smoke-test"), ("--shell-smoke-test",)):
            subprocess.run(
                [str(executable), *flags], cwd=cwd, env=environment,
                check=True, timeout=60,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Kadoka Tools one-dir distribution")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Test both frozen UIs, including real Tk creation for the workspace.",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or root / "dist").resolve()
    executable = build(root, output)
    if args.smoke_test:
        run_smoke_test(executable)
    print(f"one-dir build ready: {executable.parent}")


if __name__ == "__main__":
    main()
