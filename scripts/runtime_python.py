"""Resolve Python interpreters without depending on a former C: install.

The project keeps application virtual environments beside each backend, while
the base Python installation is configured through ``KADOKA_PYTHON_ROOT``.
This module is intentionally stdlib-only so every launcher can use it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def python_root() -> Path | None:
    """Return the standalone Python root only when the user configured one."""
    configured = os.environ.get("KADOKA_PYTHON_ROOT", "").strip()
    return Path(configured).expanduser() if configured else None


def is_frozen() -> bool:
    """Return whether the current process is a PyInstaller-frozen executable."""
    return bool(getattr(sys, "frozen", False))


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


def venv_python(venv_dir: Path, *, windowed: bool = False) -> Path:
    """Resolve a venv interpreter, with a portable base-Python fallback."""
    executable = "pythonw.exe" if windowed else "python.exe"
    candidate = Path(venv_dir) / "Scripts" / executable
    if candidate.is_file():
        return candidate
    return preferred_python()
