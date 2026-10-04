from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
import tokenize
from collections import Counter
from pathlib import Path
from typing import Literal

STATUS = Literal["covered", "uncovered", "unrecognized"]
Declaration = tuple[str, int, str, str, STATUS]
SourceError = tuple[str, int, str]
ScanResult = tuple[tuple[Declaration, ...], tuple[SourceError, ...]]
BudgetViolation = tuple[str, int, int]
BASELINE_SCHEMA_VERSION = 1
BASELINE_NAME = "tools/architecture/comment_coverage_baseline.json"
EXCLUDED_DIRECTORY_NAMES = {
    ".git", ".venv", "venv", "__pycache__", ".cache", ".pytest_cache",
    "cache", "caches", "output", "outputs", "user_data", "models",
    "checkpoints", "wildcards", "external", "vendor", "vendors",
    "third_party", "third-party", "generated",
    "node_modules", "site-packages",
}
ROOT_OUTPUT_DIRECTORY_NAMES = {"build", "dist"}
DECLARATION_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


# {
# 責務: [is_in_scope: パスがfirst-party Python検査対象か判定する]
# 処理: [1: Python拡張子を確認する, 2: 生成物と外部データのパスを除く,
# 3: 対象可否を返す]
# 引数: [path: リポジトリ相対パス]
# 戻り値: [対象ならTrue]
# }
def is_in_scope(path: str) -> bool:
    normalized = Path(path.replace("\\", "/"))
    if normalized.is_absolute() or any(part in {".", ".."} for part in normalized.parts):
        return False
    if normalized.suffix.lower() != ".py":
        return False
    if normalized.parts and normalized.parts[0].lower() in ROOT_OUTPUT_DIRECTORY_NAMES:
        return False
    if any(part.lower() in EXCLUDED_DIRECTORY_NAMES for part in normalized.parts):
        return False
    return not normalized.name.lower().endswith("_pb2.py")


# {
# 責務: [tracked_python_files: Git追跡中の対象Pythonファイルを列挙する]
# 処理: [1: Gitの追跡パスを取得する, 2: 除外条件を適用する,
# 3: パス順に整列する]
# 引数: [root: Gitリポジトリのルート]
# 戻り値: [対象ファイルの相対パス一覧]
# }
def tracked_python_files(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", "*.py"],
        check=True,
        capture_output=True,
    )
    paths = completed.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return sorted(path for path in paths if path and is_in_scope(path))


# {
# 責務: [declaration_start_line: decoratorを含む宣言の先頭行を求める]
# 処理: [1: decoratorがあれば最初のdecorator行を返す,
# 2: なければ宣言行を返す]
# 引数: [node: Python AST宣言ノード]
# 戻り値: [宣言に属する構文の最初の行番号]
# }
def declaration_start_line(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", ())
    return min(item.lineno for item in decorators) if decorators else node.lineno  # type: ignore[attr-defined]


# {
# 責務: [preceding_comment_block: 宣言直前に連続するコメントを取得する]
# 処理: [1: 宣言行の上からコメント行を集める,
# 2: ソース上の順に並べ直す]
# 引数: [source: Pythonソース, start_line: 宣言またはdecoratorの先頭行]
# 戻り値: [連続コメント行]
# }
def preceding_comment_block(source: str, start_line: int) -> list[str]:
    lines = source.splitlines()
    index = start_line - 2
    comments: list[str] = []
    while index >= 0 and lines[index].lstrip().startswith("#"):
        comments.append(lines[index])
        index -= 1
    return list(reversed(comments))


# {
# 責務: [strip_comment_markers: コメント行頭のPython記号を取り除く]
# 処理: [1: 各行から#と任意の空白を取り除く, 2: 行末空白を除く]
# 引数: [lines: コメント行一覧]
# 戻り値: [JSON-like内容の行一覧]
# }
def strip_comment_markers(lines: list[str]) -> list[str]:
    content: list[str] = []
    for line in lines:
        body = line.lstrip()[1:]
        content.append((body[1:] if body.startswith(" ") else body).rstrip())
    return content


# {
# 責務: [comment_block_is_recognized: コメントブロックの最小構造を検査する]
# 処理: [1: 外側の波括弧を確認する, 2: 括弧と引用符の対応を検査する,
# 3: トップレベル項目の存在を確認する]
# 引数: [lines: #を除去したコメント行]
# 戻り値: [構造が認識可能な場合はTrue]
# }
def comment_block_is_recognized(lines: list[str]) -> bool:
    meaningful = [line.strip() for line in lines if line.strip()]
    if len(meaningful) < 3 or meaningful[0] != "{" or meaningful[-1] != "}":
        return False
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    has_top_level_key = False
    matching = {"}": "{", "]": "["}
    for line in meaningful:
        if len(stack) == 1 and ":" in line:
            has_top_level_key = True
        for character in line:
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character == chr(34):
                quote = character
            elif character in "[{":
                stack.append(character)
            elif character in "]}":
                if not stack or stack[-1] != matching[character]:
                    return False
                stack.pop()
        if quote is not None:
            return False
    return not stack and has_top_level_key


# {
# 責務: [classify_declaration_comment: 宣言直前コメントの状態を分類する]
# 処理: [1: 直前コメントを取得する, 2: JSON-like開始を判定する,
# 3: 構造を検査して状態を返す]
# 引数: [source: Pythonソース, start_line: 宣言またはdecoratorの先頭行]
# 戻り値: [covered、uncovered、unrecognizedのいずれか]
# }
def classify_declaration_comment(source: str, start_line: int) -> STATUS:
    block = preceding_comment_block(source, start_line)
    if not block:
        return "uncovered"
    content = strip_comment_markers(block)
    if next((line.strip() for line in content if line.strip()), "") != "{":
        return "uncovered"
    return "covered" if comment_block_is_recognized(content) else "unrecognized"


# {
# 責務: [scan_source: 1つのPythonソースにある宣言を分類する]
# 処理: [1: ASTを解析する, 2: クラスと関数を列挙する,
# 3: 宣言前コメントを分類する]
# 引数: [path: 表示用ファイル名, source: Pythonソース]
# 戻り値: [宣言別結果と解析エラー]
# }
def scan_source(path: str, source: str) -> tuple[tuple[Declaration, ...], tuple[SourceError, ...]]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return (), ((path, exc.lineno or 0, f"Python syntax error: {exc.msg}"),)
    declarations: list[Declaration] = []
    for node in ast.walk(tree):
        if not isinstance(node, DECLARATION_TYPES):
            continue
        line = declaration_start_line(node)
        declarations.append(
            (
                path,
                line,
                node.name,
                "class" if isinstance(node, ast.ClassDef) else "function",
                classify_declaration_comment(source, line),
            )
        )
    declarations.sort(key=lambda item: (item[1], item[2]))
    return tuple(declarations), ()


# {
# 責務: [scan_repository: Git追跡対象のPython宣言を走査する]
# 処理: [1: 対象ファイルを列挙する, 2: 宣言とコメントを解析する,
# 3: 全結果を集約する]
# 引数: [root: Gitリポジトリのルート]
# 戻り値: [宣言結果とソースエラーをまとめた結果]
# }
def scan_repository(root: Path) -> ScanResult:
    declarations: list[Declaration] = []
    errors: list[SourceError] = []
    for relative_path in tracked_python_files(root):
        try:
            with tokenize.open(root / relative_path) as source_file:
                source = source_file.read()
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append((relative_path, 0, f"cannot read Python source: {exc}"))
            continue
        found, source_errors = scan_source(relative_path, source)
        declarations.extend(found)
        errors.extend(source_errors)
    return tuple(declarations), tuple(errors)


# {
# 責務: [uncovered_by_path: ファイル別の未記載宣言数を集計する]
# 処理: [1: uncovered宣言だけを数える, 2: パス順に整列する]
# 引数: [result: リポジトリ走査結果]
# 戻り値: [ファイル名から未記載数への対応]
# }
def uncovered_by_path(result: ScanResult) -> dict[str, int]:
    counts: Counter[str] = Counter(
        item[0] for item in result[0] if item[4] == "uncovered"
    )
    return dict(sorted(counts.items()))


# {
# 責務: [load_baseline: 未記載数ベースラインを検証して読み込む]
# 処理: [1: JSONを読む, 2: schemaと対象パスと数値を検証する,
# 3: 許容数を返す]
# 引数: [path: ベースラインJSONファイル]
# 戻り値: [ファイル名から許容数への対応]
# }
def load_baseline(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("baseline must be a JSON object")
    if data.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise ValueError(f"unsupported baseline schema_version: {data.get('schema_version')!r}")
    allowed = data.get("allow_uncovered")
    if not isinstance(allowed, dict):
        raise ValueError("baseline must contain an allow_uncovered object")
    result: dict[str, int] = {}
    for path_name, count in allowed.items():
        if not isinstance(path_name, str) or not is_in_scope(path_name):
            raise ValueError(f"baseline path is outside scanner scope: {path_name!r}")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError(f"baseline allowance must be non-negative for {path_name}")
        result[path_name] = count
    return result


# {
# 責務: [find_budget_violations: ファイル別許容数を超えた未記載を探す]
# 処理: [1: 現在数を得る, 2: 許容数と比較する,
# 3: 超過項目を返す]
# 引数: [result: 走査結果, allowed_uncovered: ファイル別許容数]
# 戻り値: [許容数を超えたファイル一覧]
# }
def find_budget_violations(
    result: ScanResult, allowed_uncovered: dict[str, int]
) -> tuple[BudgetViolation, ...]:
    current = uncovered_by_path(result)
    return tuple(
        (path, current.get(path, 0), allowed_uncovered.get(path, 0))
        for path in sorted(set(current) | set(allowed_uncovered))
        if current.get(path, 0) != allowed_uncovered.get(path, 0)
    )


# {
# 責務: [print_report: 走査結果を標準出力へ表示する]
# 処理: [1: 集計を表示する, 2: 不明構文と指定時の未記載を列挙する,
# 3: 解析エラーを表示する]
# 引数: [result: 走査結果, list_uncovered: 未記載宣言も列挙するか]
# 戻り値: []
# }
def print_report(result: ScanResult, list_uncovered: bool = False) -> None:
    counts = Counter(item[4] for item in result[0])
    total = len(result[0])
    print(
        f"JSON-like comment coverage: total={total} applicable={total} "
        f"covered={counts['covered']} uncovered={counts['uncovered']} "
        f"unrecognized={counts['unrecognized']} unrecognized_files={len(result[1])}"
    )
    for declaration in result[0]:
        if declaration[4] == "unrecognized":
            print(
                f"[UNRECOGNIZED] {declaration[0]}:{declaration[1]}: "
                f"{declaration[3]} {declaration[2]}"
            )
        elif list_uncovered and declaration[4] == "uncovered":
            print(
                f"[UNCOVERED] {declaration[0]}:{declaration[1]}: "
                f"{declaration[3]} {declaration[2]}"
            )
    for error in result[1]:
        print(f"[UNRECOGNIZED_SOURCE] {error[0]}:{error[1]}: {error[2]}")


# {
# 責務: [emit_baseline: 現在の未記載数をレビュー用JSONへ整形する]
# 処理: [1: 未認識構文がないことを確認する,
# 2: ファイル別未記載数をJSONにする]
# 引数: [result: 走査結果]
# 戻り値: [JSON文字列]
# }
def emit_baseline(result: ScanResult) -> str:
    counts = Counter(item[4] for item in result[0])
    if result[1] or counts["unrecognized"]:
        raise ValueError("cannot emit a baseline while source syntax/comments are unrecognized")
    data = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "description": "Per-file legacy uncovered declaration allowance; reduce as files are migrated.",
        "allow_uncovered": uncovered_by_path(result),
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# {
# 責務: [main: コマンドラインからカバレッジ検査を実行する]
# 処理: [1: 引数を解析する, 2: 追跡対象を走査する,
# 3: baselineを比較して終了コードを返す]
# 引数: [argv: オプション引数、省略時はプロセス引数]
# 戻り値: [成功0、検査失敗1、設定/実行エラー2]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report first-party Python declarations lacking JSON-like comments."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--list-uncovered", action="store_true")
    parser.add_argument("--emit-baseline", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    result = scan_repository(root)
    print_report(result, list_uncovered=args.list_uncovered)
    if args.emit_baseline:
        try:
            print(emit_baseline(result), end="")
        except ValueError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 2
        return 0
    baseline = args.baseline or root / BASELINE_NAME
    try:
        allowed = load_baseline(baseline)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot load coverage baseline {baseline}: {exc}", file=sys.stderr)
        return 2
    violations = find_budget_violations(result, allowed)
    for violation in violations:
        print(
            f"[COVERAGE_BASELINE] {violation[0]}: current uncovered="
            f"{violation[1]}, baseline={violation[2]}"
        )
    counts = Counter(item[4] for item in result[0])
    if violations or result[1] or counts["unrecognized"]:
        return 1
    print("PASS: no new uncovered declarations or unrecognized source/comments")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
