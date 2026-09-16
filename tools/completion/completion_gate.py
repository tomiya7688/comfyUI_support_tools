from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    name: str
    returncode: int


def run(command: list[str]) -> CheckResult:
    proc = subprocess.run(command)
    return CheckResult(" ".join(command), proc.returncode)


def tracked_python_files() -> list[str]:
    proc = subprocess.run(["git", "ls-files", "*.py"], check=True, capture_output=True, text=True)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def compile_check() -> CheckResult:
    files = tracked_python_files()
    if not files:
        return CheckResult("compile", 0)
    return run([sys.executable, "-m", "py_compile", *files])


def test_check() -> CheckResult:
    return run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"])


def diff_check() -> CheckResult:
    return run(["git", "diff", "--check"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run repository completion checks before commit/PR.")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args(argv)

    checks = [compile_check]
    if not args.skip_tests:
        checks.append(test_check)
    checks.append(diff_check)

    for check in checks:
        try:
            result = check()
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"FAIL: {check.__name__}: {exc}", file=sys.stderr)
            return 2
        if result.returncode != 0:
            print(f"FAIL: {result.name}", file=sys.stderr)
            return result.returncode or 1
        print(f"PASS: {result.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
