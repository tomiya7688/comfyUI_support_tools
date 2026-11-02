from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass


# {
#   責務: [
#     CheckResult: 一つのcompletion commandのlabelとreturn codeを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     name: str field stored by this declaration,
#     returncode: int field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     CheckResult: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class CheckResult:
    name: str
    returncode: int


# {
#   責務: [
#     run: subprocess commandを実行し、labelと成功状態を表示する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     command: subprocess argument vector (list[str]),
#   ],
#   戻り値: [
#     result: CheckResult as described by the annotated return type,
#   ],
#   副作用: [
#     external processを起動し、結果を取得する,
#   ],
# }
def run(command: list[str]) -> CheckResult:
    proc = subprocess.run(command)
    return CheckResult(" ".join(command), proc.returncode)


# {
#   責務: [
#     tracked_python_files: gitが追跡するPython filesを列挙する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: list[str] as described by the annotated return type,
#   ],
#   副作用: [
#     external processを起動し、結果を取得する,
#   ],
# }
def tracked_python_files() -> list[str]:
    proc = subprocess.run(["git", "ls-files", "*.py"], check=True, capture_output=True, text=True)
    return [line for line in proc.stdout.splitlines() if line.strip()]


# {
#   責務: [
#     compile_check: tracked Python filesをpy_compileで構文検査する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: CheckResult as described by the annotated return type,
#   ],
# }
def compile_check() -> CheckResult:
    files = tracked_python_files()
    if not files:
        return CheckResult("compile", 0)
    return run([sys.executable, "-m", "py_compile", *files])


# {
# 責務: [ quality_check: incremental code quality gateをcompletion gateから実行する ]
# 処理: [ 1: quality_gate.pyを実行する, 2: 結果を返す ]
# 引数: []
# 戻り値: [ result: 品質gateのCheckResult ]
# }
def quality_check() -> CheckResult:
    return run([sys.executable, "tools/quality/quality_gate.py"])


# {
#   責務: [comment_coverage_check: 移行済みsource areasの宣言comment coverageをstrictに検査する]
#   処理: [移行済み領域ごとのpath filterでcoverage checkerを実行し、そのstatusを返す]
#   引数: []
#   戻り値: [result: coverage checkerのCheckResult]
#   副作用: [coverage checker subprocessを起動する]
# }
def comment_coverage_check() -> CheckResult:
    return run(
        [
            sys.executable,
            "tools/quality/comment_coverage.py",
            "--path",
            "tools",
            "--path",
            "tests",
            "--path",
            "src/comfyui_support_tools/shared",
            "--path",
            "src/comfyui_support_tools/entrypoints",
            "--path",
            "src/comfyui_support_tools/applications/sequence",
            "--path",
            "src/comfyui_support_tools/applications/main_gui",
            "--path",
            "nuno/_touka/fashionpedia_preset_builder.py",
            "--path",
            "nuno/_touka/fashionpedia_segmentation_model.py",
            "--path",
            "nuno/_touka/fashionpedia_training_dataset.py",
            "--path",
            "nuno/_touka/guidance.py",
            "--path",
            "nuno/_touka/image_enhancer.py",
            "--path",
            "nuno/_touka/material_estimator.py",
            "--path",
            "nuno/_touka/touka_batch.py",
            "--path",
            "nuno/_touka/train_fashionpedia_segmentation.py",
            "--path",
            "nuno/_touka/translucent_surface_augmenter.py",
            "--path",
            "scripts/__init__.py",
            "--path",
            "scripts/app.py",
            "--path",
            "scripts/context.py",
            "--path",
            "scripts/context_packet.py",
            "--path",
            "scripts/runtime_python.py",
            "--path",
            "scripts/services.py",
            "--path",
            "scripts/subapp_runtime.py",
            "--path",
            "scripts/tab_catalog.py",
            "--path",
            "scripts/widgets",
            "--path",
            "tabbed_tools_gui.py",
            "--path",
            "tabbed_tool_gui.py",
            "--path",
            "scripts/tabs",
            "--path",
            "scripts/backend",
            "--strict",
        ]
    )


# {
#   責務: [
#     test_check: repository unittest suiteを実行する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: CheckResult as described by the annotated return type,
#   ],
# }
def test_check() -> CheckResult:
    return run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-t",
            ".",
            "-p",
            "test_*.py",
        ]
    )


# {
#   責務: [
#     generated_docs_check: generated documentationが最新かを検査する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: CheckResult as described by the annotated return type,
#   ],
# }
def generated_docs_check() -> CheckResult:
    return run([sys.executable, "tools/docs/generate_docs.py", "--check"])


# {
#   責務: [
#     architecture_check: application boundary architecture checkerを実行する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: CheckResult as described by the annotated return type,
#   ],
# }
def architecture_check() -> CheckResult:
    return run([sys.executable, "tools/architecture/app_boundary_check.py"])


# {
#   責務: [
#     upd_architecture_check: UPD architecture boundary checkerを実行する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: CheckResult as described by the annotated return type,
#   ],
# }
def upd_architecture_check() -> CheckResult:
    return run([sys.executable, "tools/architecture/upd_check.py"])


# {
#   責務: [
#     diff_check: git diff whitespace checkを実行する
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: CheckResult as described by the annotated return type,
#   ],
# }
def diff_check() -> CheckResult:
    return run(["git", "diff", "--check"])


# {
#   責務: [
#     main: repository completion checksを順番に実行し、最初の失敗を終了statusとして返す
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--skip-tests),
#     2: repository completion checksを順番に実行し、最初の失敗を終了statusとして返す,
#     3: resultとexit statusを返す,
#   ],
#   引数: [
#     argv: command-line argument vector (list[str] | None),
#   ],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     各completion checkのexternal processを起動する,
#     check結果とerrorを標準出力または標準errorへ表示する,
#   ],
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run repository completion checks before commit/PR."
    )
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args(argv)

    checks = [compile_check, quality_check, comment_coverage_check]
    if not args.skip_tests:
        checks.append(test_check)
    checks.extend([generated_docs_check, architecture_check, upd_architecture_check, diff_check])

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
