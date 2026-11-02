from __future__ import annotations

import re
import subprocess
from dataclasses import asdict, dataclass


# {
#   責務: [
#     DiffContext: base-relative git change summaryとpatch excerptを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     changed_files: list[str] field stored by this declaration,
#     changed_symbols: list[str] field stored by this declaration,
#     patch_lines: list[str] field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     DiffContext: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class DiffContext:
    changed_files: list[str]
    changed_symbols: list[str]
    patch_lines: list[str]


_SYMBOL_PATTERNS = (
    re.compile(r"^@@.*@@\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"^[+-]\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"),
)


# {
#   責務: [
#     _run_git: repository rootでgit commandを実行してstdoutを返す
#   ],
#   処理: [
#     1: 必要なexternal commandを実行しreturn statusを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     args: parsed CLI arguments (list[str]),
#   ],
#   戻り値: [
#     result: str as described by the annotated return type,
#   ],
#   副作用: [
#     external processを起動し、結果を取得する,
#   ],
# }
def _run_git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
    return proc.stdout


# {
#   責務: [
#     collect_diff_context: git diff, changed paths, source hunksからcompact contextを収集する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     base: git base reference (str),
#     max_patch_lines: maximum patch lines to retain (int),
#   ],
#   戻り値: [
#     result: DiffContext as described by the annotated return type,
#   ],
# }
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


# {
#   責務: [
#     to_dict: DiffContext dataclassをJSON-compatible dictionaryへ変換する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     context: collected diff context (DiffContext),
#   ],
#   戻り値: [
#     result: dict[str, object] as described by the annotated return type,
#   ],
# }
def to_dict(context: DiffContext) -> dict[str, object]:
    return asdict(context)
