"""Run the offline, change-aware self-check before opening a pull request."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


# {
#   責務: [LocalCheckResult: local checkの状態を一つのsummaryに保持する]
#   フィールド: [name、status、detail]
# }
@dataclass(frozen=True)
class LocalCheckResult:
    name: str
    status: str
    detail: str = ""


# {
#   責務: [project_root: script位置からrepository rootを求める]
#   処理: [1: current fileを解決する 2: repository root parentを返す]
#   引数: []
#   戻り値: [root: project root]
# }
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


# {
#   責務: [git: repository rootでgit commandを実行する]
#   処理: [1: git subprocessをrunする 2: resultまたは明示errorを返す]
#   引数: [root: repository root, args: git arguments]
#   戻り値: [result: CompletedProcess]
# }
def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


# {
#   責務: [select_base: local diff checks用のbase refを決定する]
#   処理: [1: environment override/GitHub baseを優先する 2: existing main refsへfallbackする]
#   引数: [root: repository root]
#   戻り値: [base: usable ref or None]
# }
def select_base(root: Path) -> str | None:
    candidates = [os.environ.get("LOCAL_CHECK_BASE")]
    github_base = os.environ.get("GITHUB_BASE_REF")
    if github_base:
        candidates.append(f"origin/{github_base}")
    candidates.extend(("origin/main", "main", "HEAD^"))
    for candidate in candidates:
        if candidate and git(root, "rev-parse", "--verify", "--quiet", candidate).returncode == 0:
            return candidate
    return None


# {
#   責務: [changed_paths: committed/working/untracked change pathsを一意に集める]
#   処理: [1: base diffとHEAD diffを読む 2: untrackedを加えてsortする]
#   引数: [root: repository root, base: comparison ref]
#   戻り値: [paths: changed repository-relative file paths]
# }
def changed_paths(root: Path, base: str) -> tuple[str, ...]:
    paths = set()
    for args in (("diff", "--name-only", f"{base}...HEAD"), ("diff", "--name-only", "HEAD")):
        result = git(root, *args)
        if result.returncode:
            raise RuntimeError(
                result.stderr.strip() or "git diff could not determine changed files"
            )
        paths.update(item for item in result.stdout.splitlines() if item)
    untracked = git(root, "ls-files", "--others", "--exclude-standard")
    if untracked.returncode:
        raise RuntimeError(untracked.stderr.strip() or "git could not list untracked files")
    paths.update(item for item in untracked.stdout.splitlines() if item)
    return tuple(sorted(paths))


# {
#   責務: [is_project_python: project-owned Python pathだけをlocal syntax/quality targetにする]
#   処理: [1: .py suffixを確認する 2: third-party/generated exclusionsを除く]
#   引数: [path: repository-relative path]
#   戻り値: [included: project-owned Pythonならtrue]
# }
def is_project_python(path: str) -> bool:
    normalized = Path(path).as_posix()
    excluded = ("external/", "licenses/", "doc/generated/")
    return normalized.endswith(".py") and not normalized.startswith(excluded)


# {
#   責務: [run_command: named check subprocessを実行してresultを作る]
#   処理: [1: commandを実行する 2: PASS/FAILと短いoutputを返す]
#   引数: [root: cwd, name: check label, command: argv]
#   戻り値: [result: check result]
# }
def run_command(root: Path, name: str, command: list[str]) -> LocalCheckResult:
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    except OSError as error:
        return LocalCheckResult(name, "FAIL", f"could not start: {error}")
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    detail = output[-1600:] if output else ""
    return LocalCheckResult(name, "PASS" if completed.returncode == 0 else "FAIL", detail)


# {
#   責務: [compile_changed_python: changed Python sourceをfile writeなしでsyntax compileする]
#   処理: [1: UTF-8 sourceを読む 2: builtin compileで各fileを検査する]
#   引数: [root: repository root, paths: changed Python paths]
#   戻り値: [result: PASS/FAIL/SKIP summary]
# }
def compile_changed_python(root: Path, paths: tuple[str, ...]) -> LocalCheckResult:
    python_files = tuple(
        path for path in paths if is_project_python(path) and (root / path).is_file()
    )
    if not python_files:
        return LocalCheckResult("Python syntax", "SKIP", "no changed Python files")
    errors = []
    for relative_path in python_files:
        source_path = root / relative_path
        try:
            source = source_path.read_text(encoding="utf-8")
            compile(source, str(source_path), "exec")
        except (OSError, UnicodeError, SyntaxError) as error:
            errors.append(f"{relative_path}: {type(error).__name__}: {error}")
    return LocalCheckResult(
        "Python syntax",
        "FAIL" if errors else "PASS",
        "\n".join(errors) if errors else f"compiled {len(python_files)} changed file(s) in memory",
    )


# {
#   責務: [target_test_command: changed test pathsをunittest module namesへ変換する]
#   処理: [1: tests package配下のtest_*.pyを選ぶ 2: no specific tests時はfull discoveryへfallbackする]
#   引数: [paths: changed paths, has_python_changes: source/test Python change flag]
#   戻り値: [command: unittest argv or None]
# }
def target_test_command(paths: tuple[str, ...], has_python_changes: bool) -> list[str] | None:
    tests = tuple(
        path
        for path in paths
        if path.startswith("tests/")
        and Path(path).name.startswith("test_")
        and path.endswith(".py")
    )
    if tests:
        modules = [Path(path).with_suffix("").as_posix().replace("/", ".") for path in tests]
        return [sys.executable, "-m", "unittest", *modules]
    if has_python_changes:
        return [
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
    return None


# {
#   責務: [test_count_is_nonzero: unittest outputからcollected test countを判定する]
#   処理: [1: Ran N tests summaryをparseする 2: N>0のみtrueにする]
#   引数: [output: combined unittest output]
#   戻り値: [has_tests: at least one test ran]
# }
def test_count_is_nonzero(output: str) -> bool:
    match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    return bool(match and int(match.group(1)) > 0)


# {
#   責務: [check_untracked_whitespace: untracked text filesのtrailing whitespaceを検出する]
#   処理: [1: UTF-8 decode可能なuntrackedを読む 2: trailing spaces/tabsを報告する]
#   引数: [root: repository root, paths: changed paths]
#   戻り値: [result: whitespace check]
# }
def check_untracked_whitespace(root: Path, paths: tuple[str, ...]) -> LocalCheckResult:
    untracked = git(root, "ls-files", "--others", "--exclude-standard")
    if untracked.returncode:
        return LocalCheckResult("untracked whitespace", "FAIL", untracked.stderr.strip())
    names = set(untracked.stdout.splitlines())
    findings = []
    for relative_path in paths:
        if relative_path not in names:
            continue
        path = root / relative_path
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        findings.extend(
            f"{relative_path}:{line_number}: trailing whitespace"
            for line_number, line in enumerate(text.splitlines(), 1)
            if line.endswith((" ", "\t"))
        )
    return LocalCheckResult(
        "untracked whitespace",
        "FAIL" if findings else ("PASS" if names.intersection(paths) else "SKIP"),
        "\n".join(findings)
        if findings
        else "checked new text files"
        if names.intersection(paths)
        else "no untracked changed files",
    )


# {
#   責務: [run_local_checks: diff/syntax/quality/tests/docsを順番に実行しsingle resultを返す]
#   処理: [1: base/change scopeを確定する 2:必須checkを選択する 3: summaryとexit codeを出す]
#   引数: [root: repository root]
#   戻り値: [code: zero only when every applicable required check passed]
# }
def run_local_checks(root: Path) -> int:
    results: list[LocalCheckResult] = []
    base = select_base(root)
    if base is None:
        results.append(
            LocalCheckResult(
                "base ref", "UNVERIFIED", "no usable base ref; fetch origin or set LOCAL_CHECK_BASE"
            )
        )
        return _print_summary(results)
    try:
        paths = changed_paths(root, base)
    except RuntimeError as error:
        results.append(LocalCheckResult("changed file discovery", "FAIL", str(error)))
        return _print_summary(results)
    if not paths:
        results.append(
            LocalCheckResult(
                "changed file discovery",
                "UNVERIFIED",
                "no changed files found; confirm the correct branch/base",
            )
        )
        return _print_summary(results)

    results.append(
        LocalCheckResult(
            "changed file discovery", "PASS", f"base={base}; {len(paths)} changed path(s)"
        )
    )
    for args in (("diff", "--check", f"{base}...HEAD"), ("diff", "--check", "HEAD")):
        command = ["git", *args]
        results.append(run_command(root, "git diff --check", command))
        if results[-1].status == "FAIL":
            break
    results.append(check_untracked_whitespace(root, paths))

    python_changes = any(is_project_python(path) for path in paths)
    results.append(compile_changed_python(root, paths))
    quality = run_command(
        root,
        "Python quality gate",
        [
            sys.executable,
            "tools/quality/quality_gate.py",
            "--base-ref",
            base,
            "--include-untracked",
        ],
    )
    if not python_changes:
        quality = LocalCheckResult("Python quality gate", "SKIP", "no changed Python files")
    results.append(quality)

    test_command = target_test_command(paths, python_changes)
    if test_command is None:
        results.append(
            LocalCheckResult("related unit tests", "SKIP", "no changed Python source or test files")
        )
    else:
        test_result = run_command(root, "related unit tests", test_command)
        if test_result.status == "PASS" and not test_count_is_nonzero(test_result.detail):
            test_result = LocalCheckResult("related unit tests", "FAIL", "no tests were collected")
        results.append(test_result)

    results.append(
        run_command(
            root, "generated docs check", [sys.executable, "tools/docs/generate_docs.py", "--check"]
        )
    )
    return _print_summary(results)


# {
#   責務: [_print_summary: check statusesを一つの明示的summaryへ出力する]
#   処理: [1: PASS/FAIL/SKIP/UNVERIFIEDを列挙する 2: required failure時はnonzeroを返す]
#   引数: [results: ordered check results]
#   戻り値: [code: aggregate exit status]
# }
def _print_summary(results: list[LocalCheckResult]) -> int:
    print("\nLocal PR check summary")
    for result in results:
        print(f"[{result.status}] {result.name}: {result.detail or 'completed'}")
    failures = [result for result in results if result.status in {"FAIL", "UNVERIFIED"}]
    print(f"\n{'FAIL' if failures else 'PASS'}: {len(failures)} blocking check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run_local_checks(project_root()))
