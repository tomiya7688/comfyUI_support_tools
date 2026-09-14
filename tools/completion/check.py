"""Run the common pre-commit completion gate for this repository."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run(root: Path, label: str, command: list[str]) -> bool:
    print(f"[RUN] {label}: {' '.join(command)}")
    result = subprocess.run(command, cwd=root, check=False)
    if result.returncode:
        print(f"[FAIL] {label} ({result.returncode})")
        return False
    print(f"[OK] {label}")
    return True


def existing_python_roots(root: Path) -> list[str]:
    return [name for name in ("scripts", "nuno", "tools") if (root / name).exists()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ComfyUI Support Tools completion checks")
    parser.add_argument(
        "--check-generated",
        action="store_true",
        help="verify generated docs without updating them",
    )
    parser.add_argument("--skip-tests", action="store_true", help="skip unit tests")
    args = parser.parse_args()

    root = project_root()
    python = sys.executable
    docs_command = [python, "tools/docs/generate_docs.py"]
    if args.check_generated:
        docs_command.append("--check")

    checks: list[tuple[str, list[str]]] = [
        ("generated docs", docs_command),
    ]
    if not args.skip_tests and (root / "tests").exists():
        checks.append(("unit tests", [python, "-m", "unittest", "discover", "-s", "tests", "-v"]))

    roots = existing_python_roots(root)
    if roots:
        checks.append(("python compile", [python, "-m", "compileall", "-q", *roots]))

    checks.append(("git diff check", ["git", "diff", "--check"]))

    for label, command in checks:
        if not run(root, label, command):
            print("[STOP] Completion gate failed. Do not commit or open/merge a PR yet.")
            return 1

    run(root, "git status", ["git", "status", "--short"])
    print("[DONE] Completion gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
