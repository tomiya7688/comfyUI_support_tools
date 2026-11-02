"""Measure JSON-like declaration comment coverage in tracked first-party Python."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import tokenize
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

if __package__:
    from .quality_gate import _has_json_like_comment
else:
    from quality_gate import _has_json_like_comment

EXCLUDED_PREFIXES = (
    "build/",
    "dist/",
    "doc/generated/",
    "external/",
    "licenses/",
    "models/",
    "user_data/",
)
EXCLUDED_SEGMENTS = {"generated", "third_party", "vendor", "vendored"}
DECLARATION_TYPES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


# {
# 責務: [FileCoverage: 一つのsource fileにある宣言コメントの適用状況を保持する]
# フィールド: [path, total, applied, missing, undecidable]
# 処理: [集計結果を保持し、JSON reportへ変換できる]
# }
@dataclass(frozen=True)
class FileCoverage:
    path: str
    total: int
    applied: int
    missing: int
    undecidable: int


# {
# 責務: [CoverageReport: 対象fileごとのcomment coverageと全体集計を提供する]
# フィールド: [files]
# 処理: [file別結果を合算し、total/applied/missing/undecidableを返す]
# }
@dataclass(frozen=True)
class CoverageReport:
    files: tuple[FileCoverage, ...]

    # {
    # 責務: [total: report内で認識できたclass/function宣言数を返す]
    # 処理: [file別宣言数を合計する]
    # 引数: []
    # 戻り値: [total: 宣言数]
    # }
    @property
    def total(self) -> int:
        return sum(item.total for item in self.files)

    # {
    # 責務: [applied: 必須commentが認識された宣言数を返す]
    # 処理: [file別適用数を合計する]
    # 引数: []
    # 戻り値: [applied: 適用済み宣言数]
    # }
    @property
    def applied(self) -> int:
        return sum(item.applied for item in self.files)

    # {
    # 責務: [missing: 必須commentがない宣言数を返す]
    # 処理: [file別未適用数を合計する]
    # 引数: []
    # 戻り値: [missing: 未適用宣言数]
    # }
    @property
    def missing(self) -> int:
        return sum(item.missing for item in self.files)

    # {
    # 責務: [undecidable: syntax/read errorで判定できなかったfile数を返す]
    # 処理: [file別判定不能数を合計する]
    # 引数: []
    # 戻り値: [undecidable: 判定不能file数]
    # }
    @property
    def undecidable(self) -> int:
        return sum(item.undecidable for item in self.files)


# {
#   責務: [is_first_party_python: tracked Python pathがcoverage対象か判定する]
#   処理: [pathをPOSIX形式にし、除外prefix/segmentとPython拡張子を確認する]
#   引数: [path: repository-relative tracked path]
#   戻り値: [included: coverage対象ならtrue]
# }
def is_first_party_python(path: str) -> bool:
    normalized = Path(path).as_posix().removeprefix("./")
    parts = Path(normalized).parts
    return (
        normalized.endswith(".py")
        and not normalized.startswith(EXCLUDED_PREFIXES)
        and not any(part in EXCLUDED_SEGMENTS for part in parts)
    )


# {
#   責務: [analyze_source: Python source内の宣言ごとにcomment適用状況を集計する]
#   処理: [ASTをparseし、各class/function直前のJSON-like commentを検査する]
#   引数: [source: Python source text, path: report用repository-relative path]
#   戻り値: [coverage: file単位の宣言coverage]
#   エラー: [SyntaxError: sourceをASTとして解析できず判定不能]
# }
def analyze_source(source: str, path: str = "<memory>") -> FileCoverage:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return FileCoverage(path, total=0, applied=0, missing=0, undecidable=1)

    lines = source.splitlines()
    total = 0
    applied = 0
    for node in ast.walk(tree):
        if isinstance(node, DECLARATION_TYPES):
            total += 1
            if _has_json_like_comment(lines, node):
                applied += 1
    return FileCoverage(path, total, applied, total - applied, undecidable=0)


# {
# 責務: [tracked_python_files: repository内のfirst-party tracked Python pathsを取得する]
# 処理: [git ls-filesからpathsを取得し、vendored/generated/build/data領域を除外する]
# 引数: [root: repository root]
# 戻り値: [paths: 対象Python paths]
# 副作用: [git ls-files subprocessを起動する]
# エラー: [CalledProcessError: gitがtracked file一覧を取得できない]
# }
def tracked_python_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return sorted(
        path.decode("utf-8")
        for path in result.stdout.split(b"\0")
        if path and is_first_party_python(path.decode("utf-8"))
    )


# {
#   責務: [coverage_report: 選択したtracked Python filesのcomment coverageを集計する]
#   処理: [各fileを読み込み、parse/read failureをundecidableとして記録し、summaryを返す]
#   引数: [root: repository root, paths: 指定時に走査するrepository-relative paths]
#   戻り値: [report: file別およびtotal/applied/missing/undecidable coverage]
#   副作用: [対象source filesを読み込む]
# }
def coverage_report(root: Path, paths: Iterable[str] | None = None) -> CoverageReport:
    selected = list(paths) if paths is not None else tracked_python_files(root)
    resolved_root = root.resolve()
    files: list[FileCoverage] = []
    for relative in selected:
        if not is_first_party_python(relative):
            continue
        path = root / relative
        try:
            path.resolve(strict=False).relative_to(resolved_root)
            with tokenize.open(path) as source_file:
                source = source_file.read()
        except ValueError:
            # A tracked symlink can point outside the checkout; it is not first-party source.
            continue
        except (OSError, UnicodeError):
            files.append(FileCoverage(relative, 0, 0, 0, undecidable=1))
            continue
        files.append(analyze_source(source, relative))
    return CoverageReport(tuple(files))


# {
#   責務: [select_paths: user指定のpath filtersに一致するtracked filesを選ぶ]
#   処理: [path prefixを比較し、一致したfile listを返す]
#   引数: [paths: 全tracked file paths, filters: file/directory path filters]
#   戻り値: [selected: filterに一致したfile paths]
# }
def select_paths(paths: Iterable[str], filters: Iterable[str]) -> list[str]:
    normalized = tuple(Path(item).as_posix().rstrip("/") for item in filters)
    if not normalized:
        return list(paths)
    return [
        path
        for path in paths
        if any(path == item or path.startswith(item + "/") for item in normalized)
    ]


# {
#   責務: [main: coverage CLIを実行し、summary/detailを出力して終了statusを返す]
#   処理: [1: CLI argumentsをparseする, 2: tracked filesを選びcoverageを集計する, 3: strict違反を終了statusへ反映する]
#   引数: [argv: optional command-line argument vector]
#   戻り値: [status: 判定不能/未適用をstrictで検出した場合1、正常時0]
#   副作用: [git ls-files subprocessを実行し、coverage reportをstdoutへ表示する]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report JSON-like comment coverage for tracked first-party Python."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--path", action="append", default=[], help="file/directory prefix; repeatable"
    )
    parser.add_argument(
        "--strict", action="store_true", help="fail when missing or undecidable counts are nonzero"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    paths = select_paths(tracked_python_files(root), args.path)
    if args.path and not paths:
        parser.error("path filters did not match tracked Python files")
    report = coverage_report(root, paths)
    if args.json:
        print(
            json.dumps(
                {
                    "total": report.total,
                    "applied": report.applied,
                    "missing": report.missing,
                    "undecidable": report.undecidable,
                    "files": [asdict(item) for item in report.files],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            f"total={report.total} applied={report.applied} missing={report.missing} undecidable={report.undecidable}"
        )
        for item in report.files:
            if item.missing or item.undecidable:
                print(
                    f"{item.path}: total={item.total} applied={item.applied} missing={item.missing} undecidable={item.undecidable}"
                )
    return int(args.strict and (report.missing > 0 or report.undecidable > 0))


if __name__ == "__main__":
    raise SystemExit(main())
