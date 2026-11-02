"""Resolve Python interpreters without depending on a former C: install.

The project keeps application virtual environments beside each backend, while
the base Python installation is configured through ``KADOKA_PYTHON_ROOT``.
This module is intentionally stdlib-only so every launcher can use it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# {
#   責務: [python_root: configured standalone Python rootを返す]
#   処理: [read KADOKA_PYTHON_ROOT and expand it when configured]
#   引数: [なし]
#   戻り値: [Path | None]
# }
def python_root() -> Path | None:
    """Return the standalone Python root only when the user configured one."""
    configured = os.environ.get("KADOKA_PYTHON_ROOT", "").strip()
    return Path(configured).expanduser() if configured else None


# {
#   責務: [is_frozen: processがPyInstaller frozen executableかを判定する]
#   処理: [inspect sys.frozen safely and return a boolean]
#   引数: [なし]
#   戻り値: [bool]
# }
def is_frozen() -> bool:
    """Return whether the current process is a PyInstaller-frozen executable."""
    return bool(getattr(sys, "frozen", False))


# {
#   責務: [preferred_python: standalone base Python interpreterをversionとfrozen policyに従い解決する]
#   処理: [prefer configured installation, preserve explicit missing/frozen errors, or use current interpreter]
#   引数: [version]
#   戻り値: [Path]
# }
def preferred_python(version: str = "3.10") -> Path:
    """Return the preferred base interpreter without treating a frozen exe as Python."""
    root = python_root()
    if root is not None:
        candidate = root / f"python{version}" / "python.exe"
        if candidate.is_file():
            return candidate
        if is_frozen():
            raise FileNotFoundError(f"Configured Python interpreter was not found: {candidate}")
    elif is_frozen():
        raise RuntimeError("Set KADOKA_PYTHON_ROOT to use an external Python from a frozen app.")
    return Path(sys.executable)


# {
#   責務: [venv_python: virtual environment interpreterを解決しportable fallbackを提供する]
#   処理: [prefer venv executable for console/windowed mode and delegate fallback to preferred_python]
#   引数: [venv_dir, windowed]
#   戻り値: [Path]
# }
def venv_python(venv_dir: Path, *, windowed: bool = False) -> Path:
    """Resolve a venv interpreter, with a portable base-Python fallback."""
    executable = "pythonw.exe" if windowed else "python.exe"
    candidate = Path(venv_dir) / "Scripts" / executable
    if candidate.is_file():
        return candidate
    return preferred_python()
