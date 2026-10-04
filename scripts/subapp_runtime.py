from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .context import APP_DIR


# {
#   "責務": "packaged app名をexecutable上書き用環境変数keyへ変換する。",
#   "処理": ["英数字以外をunderscoreに変換しprefix付与と大文字化を行う"],
#   "引数": {"app_name": "subapp名"}, "戻り値": "環境変数key文字列"
# }
def _env_key(app_name: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in app_name).upper()
    return f"KADOKA_TOOLS_{normalized}_EXE"


# {
#   "責務": "configuredまたはapp sibling位置のpackaged executableを解決する。",
#   "処理": ["環境変数overrideを優先する", "標準候補を順に検索し見つからない場合も第一候補を返す"],
#   "引数": {"app_name": "app/executable名"}, "戻り値": "executable Path"
# }
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


# {
#   "責務": "packaged executableを直接起動しPython/venv/PATH fallbackを行わない。",
#   "処理": ["file存在を検証する", "指定引数・cwd・environmentでsubprocessを起動する"],
#   "引数": {"executable": "app Path", "args": "追加argv", "cwd": "working directory。省略可", "env": "child environment。省略可"}, "戻り値": "起動subprocess.Popen"
# }
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
