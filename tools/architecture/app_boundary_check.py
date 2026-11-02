from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


FORBIDDEN_IMPORT_PREFIXES = ("nuno", "modules", "webui")
PYTHON_COMMANDS = {"python", "python3", "py", "python.exe", "pythonw.exe"}


# {
#   責務: [
#     Violation: architecture boundary scanで検出したpath/rule/messageを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     path: str field stored by this declaration,
#     line: int field stored by this declaration,
#     rule: str field stored by this declaration,
#     message: str field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     Violation: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str


# {
#   責務: [
#     _name: AST attribute chainをqualified nameへ変換する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     node: AST node (ast.AST),
#   ],
#   戻り値: [
#     result: str as described by the annotated return type,
#   ],
# }
def _name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


# {
#   責務: [
#     scan_source: Python sourceを解析し、禁止されたimportと実行経路を違反として収集する
#   ],
#   処理: [
#     1: 対象 declarations/filesystem entriesを走査する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path: 検査または変換するfile path (str),
#     source: legacy path root (str),
#   ],
#   戻り値: [
#     result: list[Violation] as described by the annotated return type,
#   ],
# }
def scan_source(path: str, source: str) -> list[Violation]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [Violation(path, exc.lineno or 0, "ARCH000", "Python syntax error prevents boundary analysis")]

    violations: list[Violation] = []
    runtime_scope = path.replace("\\", "/").startswith("scripts/")
    tab_scope = path.replace("\\", "/").startswith("scripts/tabs/")

    for node in ast.walk(tree):
        if runtime_scope and isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORT_PREFIXES:
                    violations.append(Violation(path, node.lineno, "ARCH001", f"direct import of external app namespace: {alias.name}"))
        elif runtime_scope and isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_IMPORT_PREFIXES:
                violations.append(Violation(path, node.lineno, "ARCH001", f"direct import of external app namespace: {node.module}"))

        if tab_scope and isinstance(node, ast.Attribute) and _name(node) == "sys.executable":
            violations.append(Violation(path, node.lineno, "ARCH002", "runtime tab depends on sys.executable; launch a packaged exe or use an API instead"))

        if isinstance(node, ast.Call):
            called = _name(node.func)
            if called == "shutil.which" and node.args and isinstance(node.args[0], ast.Constant):
                value = str(node.args[0].value).lower()
                if value in PYTHON_COMMANDS:
                    violations.append(Violation(path, node.lineno, "ARCH003", f"PATH Python discovery is forbidden: {value}"))

            if called in {"subprocess.Popen", "subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output"} and node.args:
                command = node.args[0]
                if isinstance(command, (ast.List, ast.Tuple)) and command.elts:
                    first = command.elts[0]
                    if isinstance(first, ast.Constant) and str(first.value).lower() in PYTHON_COMMANDS:
                        violations.append(Violation(path, node.lineno, "ARCH003", f"PATH Python subprocess is forbidden: {first.value}"))
                    if _name(first) == "sys.executable":
                        violations.append(Violation(path, node.lineno, "ARCH004", "sys.executable must not launch another app/script"))

    return violations


# {
#   責務: [
#     load_baseline: architecture baseline JSONを読み込み、path/ruleごとの既知件数を検証する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: source/config/metadataを読み込んで解析する,
#     3: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path: 検査または変換するfile path (Path),
#   ],
#   戻り値: [
#     result: dict[tuple[str, str], tuple[int, str]] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def load_baseline(path: Path) -> dict[tuple[str, str], tuple[int, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[tuple[str, str], tuple[int, str]] = {}
    for item in data.get("allow", []):
        result[(item["path"], item["rule"])] = (int(item["max_count"]), item["reason"])
    return result


# {
#   責務: [
#     scan_repository: first-party source treeを走査してUPD境界違反を収集する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: source/config/metadataを読み込んで解析する,
#     3: 対象 declarations/filesystem entriesを走査する,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#     baseline_path: architecture baseline JSON path (Path | None),
#   ],
#   戻り値: [
#     result: tuple[list[Violation], list[str]] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def scan_repository(root: Path, baseline_path: Path | None = None) -> tuple[list[Violation], list[str]]:
    baseline = load_baseline(baseline_path or root / "tools/architecture/app_boundary_baseline.json")
    found: list[Violation] = []
    for path in sorted((root / "scripts").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        found.extend(scan_source(rel, path.read_text(encoding="utf-8")))

    counts = Counter((item.path, item.rule) for item in found)
    errors: list[str] = []
    for key, count in sorted(counts.items()):
        allowed, reason = baseline.get(key, (0, ""))
        if count > allowed:
            errors.append(f"{key[0]} {key[1]}: {count} violation(s), baseline allows {allowed}")
        elif allowed and not reason.strip():
            errors.append(f"{key[0]} {key[1]}: baseline reason is required")
    for key, (allowed, _) in sorted(baseline.items()):
        count = counts.get(key, 0)
        if count < allowed:
            errors.append(f"{key[0]} {key[1]}: baseline can be reduced from {allowed} to {count}")
    return found, errors


# {
#   責務: [
#     main: app-boundary CLIを解析し、scriptsの違反をbaselineと照合して終了statusを返す
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--root, --baseline),
#     2: app-boundary CLIを解析し、scriptsの違反をbaselineと照合して終了statusを返す,
#     3: resultとexit statusを返す,
#   ],
#   引数: [
#     argv: command-line argument vector (list[str] | None),
#   ],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     CLI結果とfindingを標準出力へ表示する,
#   ],
# }
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce API-only boundaries between packaged apps/services.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    baseline = args.baseline.resolve() if args.baseline else root / "tools/architecture/app_boundary_baseline.json"
    found, errors = scan_repository(root, baseline)
    for item in found:
        print(f"[{item.rule}] {item.path}:{item.line}: {item.message}")
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: app boundary check ({len(found)} baselined violation(s), no new violations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
