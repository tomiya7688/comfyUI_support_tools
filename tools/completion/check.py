"""Run the repository's standard, read-only local pre-PR checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import completion_gate


def _changed_paths(root: Path) -> tuple[str, ...]:
    tracked = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return tuple(sorted(set(tracked + untracked)))


def _test_modules(root: Path, changed: tuple[str, ...]) -> tuple[str, ...]:
    modules: set[str] = set()
    for name in changed:
        path = Path(name)
        if path.parts[0] == "tests" and path.suffix == ".py":
            modules.add(".".join(path.with_suffix("").parts))
            continue
        if path.suffix != ".py":
            continue
        candidate = root / "tests" / Path(*path.parts[:-1]) / f"test_{path.stem}.py"
        if candidate.is_file():
            modules.add(".".join(candidate.relative_to(root).with_suffix("").parts))
    return tuple(sorted(modules))


# {
# 責務: [ main: 変更に応じた短いローカル検査を集約して実行する ]
# 処理: [ 1: shared completion gateをunit testなしで実行する, 2: 変更に対応するテストを実行する, 3: 未検証範囲を表示する ]
# 引数: []
# 戻り値: [ status: 必須検査が成功した場合0 ]
# }
def main() -> int:
    root = Path(__file__).resolve().parents[2]
    environment_python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if environment_python.is_file() and Path(sys.executable).resolve() != environment_python.resolve():
        return subprocess.run([str(environment_python), str(Path(__file__).resolve())], check=False).returncode

    changed = _changed_paths(root)
    gate_status = completion_gate.main(["--skip-tests"])
    if gate_status:
        print("[FAIL] Shared checks failed; see the first failing check above.")
        return gate_status

    modules = _test_modules(root, changed)
    python_changes = tuple(name for name in changed if name.endswith(".py"))
    if python_changes and not modules:
        print("[UNVERIFIED] Python changes have no matching tests; add or identify focused tests.")
        return 1
    if modules:
        result = subprocess.run([sys.executable, "-m", "unittest", *modules], cwd=root, check=False)
        if result.returncode:
            print("[FAIL] Focused tests failed: " + ", ".join(modules))
            return result.returncode
        print("[PASS] Focused tests: " + ", ".join(modules))
    else:
        print("[SKIP] Focused tests: no Python files changed.")
    print("[UNVERIFIED] Full test suite and platform-specific packaging checks are left to CI.")
    print("[PASS] Local pre-PR checks completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
