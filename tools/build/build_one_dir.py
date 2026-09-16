"""Build the API-only Kadoka Tools distribution with PyInstaller."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def build(root: Path, output: Path) -> None:
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "KadokaTools", "--distpath", str(output),
        "--workpath", str(root / "build" / "pyinstaller"),
        "--specpath", str(root / "build" / "pyinstaller"),
        "--exclude-module", "torch", "--exclude-module", "torchvision",
        "--exclude-module", "torchaudio", str(root / "tabbed_tools_gui.py"),
    ]
    subprocess.run(command, cwd=root, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build API-only one-dir distribution")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.root / "dist"
    build(args.root.resolve(), output.resolve())


if __name__ == "__main__":
    main()
