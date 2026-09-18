from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .context import APP_DIR


def _env_key(app_name: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in app_name).upper()
    return f"KADOKA_TOOLS_{normalized}_EXE"


def packaged_executable(app_name: str) -> Path:
    """Resolve a packaged sibling executable without using Python/venv/PATH."""
    configured = os.environ.get(_env_key(app_name), "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    filename = app_name if app_name.lower().endswith(".exe") else f"{app_name}.exe"
    candidates = (
        APP_DIR / filename,
        APP_DIR / "apps" / Path(filename).stem / filename,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def launch_packaged_executable(
    executable: Path,
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    """Launch a packaged executable directly. No Python interpreter fallback is allowed."""
    if not executable.is_file():
        raise FileNotFoundError(f"packaged executable not found: {executable}")
    return subprocess.Popen(
        [str(executable), *map(str, args)],
        cwd=str(cwd or executable.parent),
        env=env,
        creationflags=0x00000200 if os.name == "nt" else 0,
    )
