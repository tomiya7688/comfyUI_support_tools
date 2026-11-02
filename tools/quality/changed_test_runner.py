from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.quality.quality_gate import _changed_python_files  # noqa: E402


# {
# 責務: [changed_test_modules: baseとの差分に含まれるtest module名を得る]
# 処理: [1: changed Python fileを取得する 2: tests配下だけmodule名へ変換する]
# 引数: [root: repository root, base_ref: comparison ref]
# 戻り値: [module names]
# }
def changed_test_modules(root: Path, base_ref: str | None) -> tuple[str, ...]:
    changes = _changed_python_files(root, base_ref, all_files=False)
    return tuple(
        path[:-3].replace("/", ".")
        for path in changes.files
        if path.startswith("tests/") and Path(path).name.startswith("test_")
    )


# {
# 責務: [main: changed testsをunittestで実行する]
# 処理: [1: changed test moduleを得る 2: unittestを実行する 3: statusを返す]
# 引数: [argv: command-line arguments]
# 戻り値: [exit status]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run test modules changed from the selected base.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--base-ref")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    modules = changed_test_modules(root, args.base_ref)
    if not modules:
        print("OK: no changed test modules")
        return 0
    result = subprocess.run(
        [sys.executable, "-m", "unittest", *modules],
        cwd=root,
        check=False,
    )
    if result.returncode == 0:
        print(f"OK: changed test modules ({len(modules)})")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
