from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class DiffContext:
    changed_files: list[str]
    changed_symbols: list[str]
    patch_lines: list[str]


_SYMBOL_PATTERNS = (
    re.compile(r"^@@.*@@\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^[+-]\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"),
)


def _run_git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return proc.stdout


def collect_diff_context(base: str = "main", max_patch_lines: int = 80) -> DiffContext:
    try:
        changed_files = [
            line.strip()
            for line in _run_git(["diff", "--name-only", f"{base}...HEAD"]).splitlines()
            if line.strip()
        ]
        diff = _run_git(["diff", "--unified=0", f"{base}...HEAD", "--", "*.py"])
    except (OSError, subprocess.CalledProcessError):
        return DiffContext([], [], [])

    symbols: list[str] = []
    patch_lines: list[str] = []
    for raw in diff.splitlines():
        if raw.startswith(("diff --git ", "index ", "--- ", "+++ ")):
            continue
        for pattern in _SYMBOL_PATTERNS:
            match = pattern.match(raw)
            if match and match.group(1) not in symbols:
                symbols.append(match.group(1))
                break
        if raw.startswith(("@@", "+", "-")) and len(patch_lines) < max_patch_lines:
            patch_lines.append(raw[:240])

    return DiffContext(changed_files[:30], symbols[:30], patch_lines)


def to_dict(context: DiffContext) -> dict[str, object]:
    return asdict(context)
