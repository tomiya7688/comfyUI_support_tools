"""Build the Kadoka Tools one-dir distribution with PyInstaller."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

APP_NAME = "KadokaTools"
EXCLUDED_MODULES = ("torch", "torchvision", "torchaudio")


def executable_path(output: Path) -> Path:
    suffix = ".exe" if os.name == "nt" else ""
    return output / APP_NAME / f"{APP_NAME}{suffix}"


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
    ]
    for module_name in EXCLUDED_MODULES:
        command.extend(("--exclude-module", module_name))
    command.append(str(root / "tabbed_tools_gui.py"))

    subprocess.run(command, cwd=root, check=True)

    distribution_dir = output / APP_NAME
    (distribution_dir / "user_data" / "input" / "config" / "common").mkdir(
        parents=True,
        exist_ok=True,
    )
    executable = executable_path(output)
    if not executable.is_file():
        raise FileNotFoundError(f"PyInstaller output executable was not created: {executable}")
    return executable


def run_smoke_test(executable: Path) -> None:
    subprocess.run([str(executable), "--smoke-test"], cwd=executable.parent, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Kadoka Tools one-dir distribution")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run the frozen executable in import-only smoke-test mode after building.",
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
