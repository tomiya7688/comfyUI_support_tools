"""Run the common pre-commit completion gate for this repository."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


# {
#   責務: [
#     project_root: tools module位置からrepository rootを解決する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: Path as described by the annotated return type,
#   ],
# }
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


# {
#   責務: [
#     run: subprocess commandを実行し、labelと成功状態を表示する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#     label: command label shown in output (str),
#     command: subprocess argument vector (list[str]),
#   ],
#   戻り値: [
#     result: bool as described by the annotated return type,
#   ],
#   副作用: [
#     external processを起動し、結果を取得する,
#     CLI status、finding、またはerrorを標準出力へ表示する,
#   ],
# }
def run(root: Path, label: str, command: list[str]) -> bool:
    print(f"[RUN] {label}: {' '.join(command)}")
    result = subprocess.run(command, cwd=root, check=False)
    if result.returncode:
        print(f"[FAIL] {label} ({result.returncode})")
        return False
    print(f"[OK] {label}")
    return True


# {
#   責務: [
#     existing_python_roots: workspace内で既に存在するPython runtime rootsを列挙する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: list[str] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def existing_python_roots(root: Path) -> list[str]:
    return [name for name in ("scripts", "nuno", "tools") if (root / name).exists()]


# {
#   責務: [
#     main: 指定されたcompletion checkを1件実行し、その結果statusを返す
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--check-generated, --skip-tests),
#     2: 指定されたcompletion checkを1件実行し、その結果statusを返す,
#     3: resultとexit statusを返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     completion commandのexternal processを起動する,
#   ],
# }
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
        checks.append(
            ("unit tests", [python, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"])
        )

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
