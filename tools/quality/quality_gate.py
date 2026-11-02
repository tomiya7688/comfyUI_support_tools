from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_PREFIXES = ("external/", "licenses/", "doc/generated/")
STRICT_NEW_RULES = "E4,E7,E9,F,I,B,UP"
HUNK_RE = re.compile(r"^@@ -\\d+(?:,\\d+)? \\+(\\d+)(?:,(\\d+))? @@")
PRECISION_TERMS = ("evaluator", "ranking", "calibration", "metric", "precision", "scoring")


# {
# 責務: [ Finding: 品質検査結果1件を表現する ]
# フィールド: [ severity: 重大度, rule: rule ID, path: file, line: 行, message: 内容 ]
# 処理: []
# }
@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    path: str
    line: int
    message: str


# {
# 責務: [ ChangeSet: 品質検査対象の変更集合を保持する ]
# フィールド: [ files: 変更file, new_files: 新規file, base_commit: 比較元commit ]
# 処理: []
# }
@dataclass(frozen=True)
class ChangeSet:
    files: tuple[str, ...]
    new_files: frozenset[str]
    base_commit: str | None


# {
# 責務: [ _run_git: repository rootでgit commandを実行する ]
# 処理: [ 1: gitを実行する, 2: 結果を返す ]
# 引数: [ root: repository root, args: git引数, check: error化指定 ]
# 戻り値: [ result: subprocess結果 ]
# }
def _run_git(
    root: Path, args: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# {
# 責務: [ _ref_exists: git refの存在を確認する ]
# 処理: [ 1: rev-parseする, 2: 存在有無を返す ]
# 引数: [ root: repository root, ref: git ref ]
# 戻り値: [ exists: refが存在する場合true ]
# }
def _ref_exists(root: Path, ref: str) -> bool:
    return _run_git(root, ["rev-parse", "--verify", "--quiet", ref], check=False).returncode == 0


# {
# 責務: [ _choose_base_ref: 差分検査の比較元refを選ぶ ]
# 処理: [ 1: 明示refとCI refを候補化する, 2: main系へfallbackする ]
# 引数: [ root: repository root, requested: 明示ref ]
# 戻り値: [ base_ref: 使用可能refまたはNone ]
# }
def _choose_base_ref(root: Path, requested: str | None) -> str | None:
    candidates = [requested, os.environ.get("QUALITY_BASE_REF")]
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base:
        candidates.append(f"origin/{github_base}")
    candidates.extend(["origin/main", "main"])
    return next((ref for ref in candidates if ref and _ref_exists(root, ref)), None)


# {
# 責務: [ _merge_base: HEADとbase refの共通祖先を取得する ]
# 処理: [ 1: merge-baseを実行する, 2: SHAを返す ]
# 引数: [ root: repository root, base_ref: 比較元ref ]
# 戻り値: [ commit: merge-base SHA ]
# }
def _merge_base(root: Path, base_ref: str) -> str:
    return _run_git(root, ["merge-base", "HEAD", base_ref]).stdout.strip()


# {
# 責務: [ _project_python_path: project-owned Python pathか判定する ]
# 処理: [ 1: pathを正規化する, 2: Pythonと除外領域を判定する ]
# 引数: [ path: repository相対path ]
# 戻り値: [ included: 検査対象の場合true ]
# }
def _project_python_path(path: str) -> bool:
    normalized = Path(path).as_posix()
    return normalized.endswith(".py") and not normalized.startswith(EXCLUDED_PREFIXES)


# {
# 責務: [ _changed_python_files: 差分Python fileを収集する ]
# 処理: [ 1: 比較元を決める, 2: git diffを読む, 3: 対象fileを返す ]
# 引数: [ root: repository root, requested_base_ref: 明示ref, all_files: 全file指定 ]
# 戻り値: [ changes: ChangeSet ]
# }
def _changed_python_files(
    root: Path,
    requested_base_ref: str | None,
    *,
    all_files: bool,
    include_untracked: bool = False,
) -> ChangeSet:
    if all_files:
        files = tuple(
            sorted(
                path
                for path in _run_git(root, ["ls-files", "*.py"]).stdout.splitlines()
                if _project_python_path(path)
            )
        )
        return ChangeSet(files, frozenset(), None)

    base_ref = _choose_base_ref(root, requested_base_ref)
    base_commit = _merge_base(root, base_ref) if base_ref else None
    args = ["diff", "--name-status", "--diff-filter=ACMR", base_commit or "HEAD", "--", "*.py"]
    statuses: dict[str, str] = {}
    for raw in _run_git(root, args).stdout.splitlines():
        parts = raw.split("\t")
        if len(parts) >= 2 and _project_python_path(parts[-1]):
            statuses[parts[-1]] = parts[0]
    if include_untracked:
        for path in _run_git(
            root, ["ls-files", "--others", "--exclude-standard", "--", "*.py"]
        ).stdout.splitlines():
            if _project_python_path(path):
                statuses[path] = "A"
    return ChangeSet(
        tuple(sorted(statuses)),
        frozenset(path for path, status in statuses.items() if status.startswith("A")),
        base_commit,
    )


# {
# 責務: [ _added_line_ranges: 現在側に追加された行rangeを取得する ]
# 処理: [ 1: 新規fileを全行扱いする, 2: diff hunkを解析する ]
# 引数: [ root: repository root, path: file, base_commit: 比較元, is_new: 新規判定, line_count: 行数 ]
# 戻り値: [ ranges: 追加行range ]
# }
def _added_line_ranges(
    root: Path,
    path: str,
    base_commit: str | None,
    *,
    is_new: bool,
    line_count: int,
) -> tuple[tuple[int, int], ...]:
    if is_new:
        return ((1, max(line_count, 1)),)
    if base_commit is None:
        return ()
    ranges: list[tuple[int, int]] = []
    for line in _run_git(
        root, ["diff", "--unified=0", base_commit, "--", path]
    ).stdout.splitlines():
        match = HUNK_RE.match(line)
        if match:
            start, count = int(match.group(1)), int(match.group(2) or "1")
            if count:
                ranges.append((start, start + count - 1))
    return tuple(ranges)


# {
# 責務: [ _line_in_ranges: 行が追加range内か判定する ]
# 処理: [ 1: rangeを走査する, 2: 含有結果を返す ]
# 引数: [ line: 行番号, ranges: 追加range ]
# 戻り値: [ included: 追加行ならtrue ]
# }
def _line_in_ranges(line: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= line <= end for start, end in ranges)


# {
# 責務: [ _declaration_start: decoratorを含む宣言開始行を返す ]
# 処理: [ 1: decorator行を集める, 2: 最小行を返す ]
# 引数: [ node: class/function node ]
# 戻り値: [ line: 宣言開始行 ]
# }
def _declaration_start(node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    return min([node.lineno, *(item.lineno for item in node.decorator_list)])


# {
# 責務: [ _comment_block_before: 宣言直前comment blockを取得する ]
# 処理: [ 1: 空行を読み飛ばす, 2: 連続commentを収集する ]
# 引数: [ lines: source行, declaration_line: 宣言開始行 ]
# 戻り値: [ block: comment text ]
# }
def _comment_block_before(lines: list[str], declaration_line: int) -> str:
    index = declaration_line - 2
    while index >= 0 and not lines[index].strip():
        index -= 1
    collected: list[str] = []
    while index >= 0 and lines[index].lstrip().startswith("#"):
        collected.append(lines[index].strip())
        index -= 1
    return "\n".join(reversed(collected))


# {
# 責務: [ _has_json_like_comment: 宣言commentが恒久comment規約を満たすか判定する ]
# 処理: [ 1: comment blockを取る, 2: 必須Semantic Keyを確認する ]
# 引数: [ lines: source行, node: class/function node ]
# 戻り値: [ valid: 規約適合ならtrue ]
# }
def _has_json_like_comment(
    lines: list[str], node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
) -> bool:
    block = _comment_block_before(lines, _declaration_start(node))
    if "# {" not in block or "# }" not in block or "責務:" not in block:
        return False
    if isinstance(node, ast.ClassDef):
        return "フィールド:" in block
    return all(key in block for key in ("処理:", "引数:", "戻り値:"))


# {
# 責務: [ _call_name: AST call targetをdotted nameへ変換する ]
# 処理: [ 1: attribute chainを収集する, 2: dotted nameを返す ]
# 引数: [ node: call target ]
# 戻り値: [ name: dotted name ]
# }
def _call_name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


# {
# 責務: [_ui_boundary_findings: legacy UIの境界越境と中央metadata重複を検出する]
# 処理: [1: application内部module importを確認する 2: central descriptor重複を確認する 3: direct IOを確認する]
# 引数: [path: repository path, node: AST node, added_ranges: added line ranges]
# 戻り値: [findings: UI boundary findings]
# }
def _ui_boundary_findings(
    path: str, node: ast.AST, added_ranges: tuple[tuple[int, int], ...]
) -> list[Finding]:
    normalized_path = path.replace("\\", "/")
    findings: list[Finding] = []
    if normalized_path.startswith("scripts/tabs/"):
        imported_modules: list[tuple[int, str]] = []
        if isinstance(node, ast.Import):
            imported_modules.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append((node.lineno, node.module))
        for line, module in imported_modules:
            if (
                _line_in_ranges(line, added_ranges)
                and ".applications." in module
                and (".data." in module or ".process.processing." in module)
            ):
                findings.append(
                    Finding(
                        "E",
                        "QUA231",
                        path,
                        line,
                        f"legacy UI imports an internal processing/data module ({module}); use an application boundary",
                    )
                )

    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = {target.id for target in targets if isinstance(target, ast.Name)}
        value = node.value
        central_names = {
            "scripts/app.py": {"tab_titles", "TAB_TITLES", "TAB_CLASSES"},
            "scripts/tab_catalog.py": {"TOOL_TAB_METADATA"},
            "scripts/widgets/tk_tab_settings_adapter.py": {"STABLE_SETTINGS_IDS"},
        }.get(normalized_path, set())
        if (
            value is not None
            and _line_in_ranges(node.lineno, added_ranges)
            and names.intersection(central_names)
            and not any(
                isinstance(item, ast.Name) and item.id == "TOOL_REGISTRY"
                for item in ast.walk(value)
            )
        ):
            findings.append(
                Finding(
                    "E",
                    "QUA232",
                    path,
                    node.lineno,
                    "central tool metadata must derive from TOOL_REGISTRY instead of a second hard-coded list",
                )
            )

    if isinstance(node, ast.Call) and _line_in_ranges(node.lineno, added_ranges):
        called = _call_name(node.func)
        is_legacy_side_effect = normalized_path.startswith("scripts/tabs/") and (
            called.startswith("subprocess.")
            or called.startswith("requests.")
            or called
            in {
                "urlopen",
                "open",
                "write_text",
                "write_bytes",
                "unlink",
                "rename",
                "replace",
                "mkdir",
                "rmdir",
            }
            or called.endswith(
                (
                    ".write_text",
                    ".write_bytes",
                    ".unlink",
                    ".rename",
                    ".replace",
                    ".mkdir",
                    ".rmdir",
                )
            )
        )
        if is_legacy_side_effect:
            findings.append(
                Finding(
                    "E",
                    "QUA230",
                    path,
                    node.lineno,
                    f"new direct I/O or process work in legacy UI ({called}); move it behind an adapter",
                )
            )
    return findings


# {
# 責務: [ scan_source: 1つのPython sourceを品質監査する ]
# 処理: [ 1: sizeと構文を確認する, 2: 新規宣言commentを確認する, 3: 危険patternを確認する ]
# 引数: [ path: file, source: source text, added_ranges: 追加行range ]
# 戻り値: [ findings: 検査結果 ]
# }
def scan_source(path: str, source: str, added_ranges: tuple[tuple[int, int], ...]) -> list[Finding]:
    lines = source.splitlines()
    findings: list[Finding] = []
    if len(lines) > 1000:
        findings.append(
            Finding(
                "A", "QUA100", path, 1, f"{len(lines)} lines: responsibility split audit required"
            )
        )
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [Finding("E", "QUA001", path, exc.lineno or 0, f"syntax error: {exc.msg}")]

    for node in ast.walk(tree):
        findings.extend(_ui_boundary_findings(path, node, added_ranges))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            size = (node.end_lineno or node.lineno) - node.lineno + 1
            if len(lines) > 1000 and _line_in_ranges(_declaration_start(node), added_ranges):
                findings.append(
                    Finding(
                        "E",
                        "QUA240",
                        path,
                        _declaration_start(node),
                        f"new function {node.name!r} added to a file over 1000 lines; split responsibilities or document an approved exception",
                    )
                )
            if size > 120:
                severity = "E" if size > 200 and _line_in_ranges(node.lineno, added_ranges) else "W"
                findings.append(
                    Finding(
                        severity,
                        "QUA110",
                        path,
                        node.lineno,
                        f"function {node.name!r} spans {size} lines",
                    )
                )
        elif isinstance(node, ast.ClassDef):
            size = (node.end_lineno or node.lineno) - node.lineno + 1
            if len(lines) > 1000 and _line_in_ranges(_declaration_start(node), added_ranges):
                findings.append(
                    Finding(
                        "E",
                        "QUA240",
                        path,
                        _declaration_start(node),
                        f"new class {node.name!r} added to a file over 1000 lines; split responsibilities or document an approved exception",
                    )
                )
            if size > 500:
                findings.append(
                    Finding(
                        "W", "QUA120", path, node.lineno, f"class {node.name!r} spans {size} lines"
                    )
                )

        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            start = _declaration_start(node)
            if _line_in_ranges(start, added_ranges) and not _has_json_like_comment(lines, node):
                findings.append(
                    Finding(
                        "E",
                        "QUA200",
                        path,
                        start,
                        f"new declaration {node.name!r} lacks JSON-like Comment Outs",
                    )
                )

        if isinstance(node, ast.ExceptHandler) and _line_in_ranges(node.lineno, added_ranges):
            if node.type is None:
                findings.append(
                    Finding("E", "QUA210", path, node.lineno, "new bare except is not allowed")
                )
            elif (
                isinstance(node.type, ast.Name)
                and node.type.id in {"Exception", "BaseException"}
                and node.body
                and all(isinstance(item, ast.Pass) for item in node.body)
            ):
                findings.append(
                    Finding(
                        "E",
                        "QUA211",
                        path,
                        node.lineno,
                        "broad exception must not be silently swallowed",
                    )
                )

        if isinstance(node, ast.Call) and _line_in_ranges(node.lineno, added_ranges):
            called = _call_name(node.func)
            if any(
                keyword.arg == "shell"
                and isinstance(keyword.value, ast.Constant)
                and keyword.value.value is True
                for keyword in node.keywords
            ):
                findings.append(
                    Finding(
                        "E",
                        "QUA220",
                        path,
                        node.lineno,
                        f"{called or 'subprocess call'} uses shell=True",
                    )
                )
            if called in {"eval", "exec"}:
                findings.append(
                    Finding(
                        "W",
                        "QUA221",
                        path,
                        node.lineno,
                        f"new {called}() requires trust-boundary review",
                    )
                )
    return findings


# {
# 責務: [precision_validation_findings: precision-sensitive changesに対応するtest追加を要求する]
# 処理: [1: changed production filesを検索する 2: test fileが無ければerrorを返す]
# 引数: [root: repository root, changed_files: changed Python paths]
# 戻り値: [findings: missing test requirement]
# }
def precision_validation_findings(root: Path, changed_files: tuple[str, ...]) -> list[Finding]:
    test_files = tuple(path for path in changed_files if path.startswith("tests/"))
    test_names = tuple(Path(path).stem.casefold() for path in test_files)
    findings: list[Finding] = []
    for path in changed_files:
        if path.startswith(("tests/", "tools/")) or not _project_python_path(path):
            continue
        source = (root / path).read_text(encoding="utf-8").casefold()
        if any(term in Path(path).stem.casefold() for term in PRECISION_TERMS) or any(
            term in source for term in PRECISION_TERMS
        ):
            module_terms = {
                term
                for term in re.split(r"[^a-z0-9]+", Path(path).stem.casefold())
                if term and term not in {"test", "quality"}
            }
            has_related_test = any(
                module_terms.intersection(re.split(r"[^a-z0-9]+", test_name))
                for test_name in test_names
            )
            if has_related_test:
                continue
            findings.append(
                Finding(
                    "E",
                    "QUA250",
                    path,
                    1,
                    "precision/evaluation/ranking changes require a changed test module with validation cases",
                )
            )
    return findings


# {
# 責務: [ _run_command: 品質tool subprocessを実行する ]
# 処理: [ 1: commandを実行する, 2: 終了codeを返す ]
# 引数: [ root: repository root, command: command ]
# 戻り値: [ returncode: 終了code ]
# }
def _run_command(root: Path, command: list[str]) -> int:
    return subprocess.run(command, cwd=root).returncode


# {
# 責務: [ _ruff_available: Ruffを利用可能か確認する ]
# 処理: [ 1: import specを検索する ]
# 引数: []
# 戻り値: [ available: Ruff利用可能ならtrue ]
# }
def _ruff_available() -> bool:
    return importlib.util.find_spec("ruff") is not None


# {
# 責務: [ _ruff_check: Ruff lintを対象fileへ実行する ]
# 処理: [ 1: commandを構築する, 2: 必要ならstrict ruleを指定する, 3: 実行する ]
# 引数: [ root: repository root, files: 対象file, strict: strict指定 ]
# 戻り値: [ returncode: Ruff終了code ]
# }
def _ruff_check(root: Path, files: tuple[str, ...], *, strict: bool) -> int:
    if not files:
        return 0
    command = [sys.executable, "-m", "ruff", "check", "--config", "ruff.toml"]
    if strict:
        command.extend(["--select", STRICT_NEW_RULES])
    return _run_command(root, [*command, *files])


# {
# 責務: [ _ruff_format_check: 新規Python fileのformat適合を検査する ]
# 処理: [ 1: Ruff format checkを実行する ]
# 引数: [ root: repository root, files: 新規file ]
# 戻り値: [ returncode: Ruff終了code ]
# }
def _ruff_format_check(root: Path, files: tuple[str, ...]) -> int:
    if not files:
        return 0
    return _run_command(
        root, [sys.executable, "-m", "ruff", "format", "--check", "--config", "ruff.toml", *files]
    )


# {
# 責務: [ main: incremental code quality gateを実行する ]
# 処理: [ 1: 対象差分を収集する, 2: AST監査する, 3: Ruff検査する, 4: 終了codeを返す ]
# 引数: [ argv: command line引数 ]
# 戻り値: [ code: process終了code ]
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Incremental code-quality gate for project-owned Python files."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--base-ref")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--include-untracked", action="store_true")
    parser.add_argument("--skip-ruff", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    changes = _changed_python_files(
        root,
        args.base_ref,
        all_files=args.all,
        include_untracked=args.include_untracked,
    )
    if not changes.files:
        print("OK: no changed project-owned Python files")
        return 0

    findings: list[Finding] = []
    for path in changes.files:
        source = (root / path).read_text(encoding="utf-8")
        ranges = _added_line_ranges(
            root,
            path,
            changes.base_commit,
            is_new=path in changes.new_files,
            line_count=len(source.splitlines()),
        )
        findings.extend(scan_source(path, source, ranges))
    findings.extend(precision_validation_findings(root, changes.files))
    for finding in findings:
        print(f"{finding.severity} {finding.rule} {finding.path}:{finding.line} {finding.message}")

    command_failed = False
    if not args.skip_ruff:
        if not _ruff_available():
            print(
                "FAIL: Ruff is required. Run: python -m pip install -r requirements-dev.txt",
                file=sys.stderr,
            )
            return 2
        command_failed |= _ruff_check(root, changes.files, strict=False) != 0
        new_files = tuple(sorted(changes.new_files))
        command_failed |= _ruff_check(root, new_files, strict=True) != 0
        command_failed |= _ruff_format_check(root, new_files) != 0

    errors = [item for item in findings if item.severity == "E"]
    if errors or command_failed:
        print(
            f"FAIL: code quality gate (errors={len(errors)}, files={len(changes.files)})",
            file=sys.stderr,
        )
        return 1
    warnings = sum(item.severity in {"W", "A"} for item in findings)
    print(f"OK: code quality gate (files={len(changes.files)}, warnings={warnings})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
