"""Resolve Python interpreters without depending on a former C: install.

The project keeps application virtual environments beside each backend, while
the base Python installation is configured through ``KADOKA_PYTHON_ROOT``.
This module is intentionally stdlib-only so every launcher can use it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


DEFAULT_PYTHON_ROOT = Path(r"E:\program_files\soft\IDE\compiler\python")


# {
#   "責務": "環境変数または既定値からstandalone Python install rootを解決する。",
#   "処理": ["KADOKA_PYTHON_ROOTを優先し未指定ならDEFAULT_PYTHON_ROOTを返す"],
#   "引数": [], "戻り値": "Python install root Path"
# }
def python_root() -> Path:
    """Return the configured standalone Python installation root."""
    configured = os.environ.get("KADOKA_PYTHON_ROOT")
    return Path(configured).expanduser() if configured else DEFAULT_PYTHON_ROOT


# {
#   "責務": "processがPyInstaller frozen executableか判定する。",
#   "処理": ["sys.frozen flagの真偽を取得する"],
#   "引数": [], "戻り値": "frozen状態bool"
# }
def is_frozen() -> bool:
    """Return whether the current process is a PyInstaller-frozen executable."""
    return bool(getattr(sys, "frozen", False))


# {
#   "責務": "frozen実行exeをPythonとして誤認せず優先base interpreterを決める。",
#   "処理": ["設定root下のversioned interpreterを選ぶ", "存在しない非frozen環境ではsys.executableへfallbackする"],
#   "引数": {"version": "Python version directory name"}, "戻り値": "preferred interpreter Path"
# }
def preferred_python(version: str = "3.10") -> Path:
    """Return the preferred base interpreter without treating a frozen exe as Python."""
    candidate = python_root() / f"python{version}" / "python.exe"
    if candidate.is_file() or is_frozen():
        return candidate
    return Path(sys.executable)


# {
#   "責務": "venv interpreterを解決し欠落時はportable base Pythonへfallbackする。",
#   "処理": ["windowed optionに合うvenv executableを確認する", "未存在ならpreferred_pythonを返す"],
#   "引数": {"venv_dir": "venv root", "windowed": "pythonw interpreterを選ぶか"}, "戻り値": "interpreter Path"
# }
def venv_python(venv_dir: Path, *, windowed: bool = False) -> Path:
    """Resolve a venv interpreter, with a portable base-Python fallback."""
    executable = "pythonw.exe" if windowed else "python.exe"
    candidate = Path(venv_dir) / "Scripts" / executable
    if candidate.is_file():
        return candidate
    return preferred_python()
