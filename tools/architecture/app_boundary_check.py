from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


FORBIDDEN_IMPORT_PREFIXES = ("nuno", "modules", "webui")
PYTHON_COMMANDS = {"python", "python3", "py", "python.exe", "pythonw.exe"}
SUBPROCESS_CALLS = {
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
}


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    message: str


def _name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _names(node: ast.AST) -> set[str]:
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def _targets(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for item in node.elts for name in _targets(item)]
    return []


def _python_interpreter_variables(tree: ast.AST) -> set[str]:
    """Find venv or PATH-resolved Python interpreters, including simple aliases."""
    variables: set[str] = set()
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
    ]
    changed = True
    while changed:
        changed = False
        for node in assignments:
            value = node.value
            if value is None:
                continue
            venv_interpreter = isinstance(value, ast.Call) and _name(value.func).endswith(
                "venv_python"
            )
            path_interpreter = any(
                isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and Path(item.value.replace("\\", "/")).name.lower() in PYTHON_COMMANDS
                for item in ast.walk(value)
            )
            if not (venv_interpreter or path_interpreter or _names(value).intersection(variables)):
                continue
            targets = (
                _targets(node.target)
                if isinstance(node, ast.NamedExpr)
                else (
                    [name for target in node.targets for name in _targets(target)]
                    if isinstance(node, ast.Assign)
                    else _targets(node.target)
                )
            )
            new = set(targets) - variables
            if new:
                variables.update(new)
                changed = True
    return variables


def _python_script_variables(tree: ast.AST) -> set[str]:
    """Recognize named paths used as backend scripts, including launch-script fields."""
    result: set[str] = set()
    assignments = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
    ]
    changed = True
    while changed:
        changed = False
        for node in assignments:
            value = node.value
            if value is None:
                continue
            value_names = _names(value)
            script_value = any(
                isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and item.value.lower().endswith(".py")
                for item in ast.walk(value)
            )
            launch_spec = any(name.lower().endswith("launch_script_name") for name in value_names)
            targets = (
                _targets(node.target)
                if isinstance(node, ast.NamedExpr)
                else (
                    [name for target in node.targets for name in _targets(target)]
                    if isinstance(node, ast.Assign)
                    else _targets(node.target)
                )
            )
            if (
                script_value
                or launch_spec
                or value_names.intersection(result)
                or any(name.lower().endswith(("_py", "_script")) for name in targets)
            ):
                new = set(targets) - result
                if new:
                    result.update(new)
                    changed = True
    return result


# {
#   責務: [_assigned_values: module内の名前と代入式の対応を収集する]
#   処理: [assignment targetごとに追跡可能な右辺式を保存する]
#   引数: [tree: 解析済みPython syntax tree]
#   戻り値: [dict[str, list[ast.AST]]: variableごとの代入式一覧]
# }
def _assigned_values(tree: ast.AST) -> dict[str, list[ast.AST]]:
    assignments: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)):
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            for name in _targets(target):
                assignments.setdefault(name, []).append(value)
    return assignments


# {
#   責務: [_command_elements: subprocess command expressionからargv要素を展開する]
#   処理: [list/tuple, concatenation, and assigned command aliasesを追跡し循環参照を止める]
#   引数: [node: command expression, assignments: variable-to-expression mapping, seen: 再帰中のalias names]
#   戻り値: [list[ast.AST]: 追跡できたargv expressions]
# }
def _command_elements(
    node: ast.AST,
    assignments: dict[str, list[ast.AST]],
    seen: frozenset[str] = frozenset(),
) -> list[ast.AST]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return list(node.elts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _command_elements(node.left, assignments, seen) + _command_elements(
            node.right, assignments, seen
        )
    if isinstance(node, ast.Name) and node.id not in seen:
        return next(
            (
                values
                for value in assignments.get(node.id, [])
                if (values := _command_elements(value, assignments, seen | {node.id}))
            ),
            [],
        )
    return [node]


# {
#   責務: [_is_python_interpreter_expression: argv先頭が追跡対象のPython interpreterか判定する]
#   処理: [venv_python calls, tracked aliases, PATH lookup, and explicit Path interpreter expressionsを認識する]
#   引数: [node: argv expression, variables: interpreterとして追跡した名前]
#   戻り値: [bool: Python interpreter expressionか]
# }
def _is_python_interpreter_expression(node: ast.AST, variables: set[str]) -> bool:
    if _names(node).intersection(variables):
        return True
    for item in ast.walk(node):
        if isinstance(item, ast.Call):
            if _name(item.func).endswith("venv_python"):
                return True
            if _name(item.func) == "shutil.which" and item.args:
                first = item.args[0]
                if isinstance(first, ast.Constant) and str(first.value).lower() in PYTHON_COMMANDS:
                    return True
    path_call = any(
        isinstance(item, ast.Call) and _name(item.func).split(".")[-1] == "Path"
        for item in ast.walk(node)
    )
    path_has_interpreter = any(
        isinstance(item, ast.Constant)
        and isinstance(item.value, str)
        and Path(item.value.replace("\\", "/")).name.lower() in PYTHON_COMMANDS
        for item in ast.walk(node)
    )
    return path_call and path_has_interpreter


# {
#   責務: [_is_python_script_expression: argvのscript位置がPython source fileを指すか判定する]
#   処理: [.py path constants, launch_script_name attributes, and tracked aliasesを認識する]
#   引数: [node: argv expression, variables: script pathとして追跡した名前]
#   戻り値: [bool: Python script expressionか]
# }
def _is_python_script_expression(node: ast.AST, variables: set[str]) -> bool:
    if _names(node).intersection(variables):
        return True
    if any(name.lower().endswith("launch_script_name") for name in _names(node)):
        return True
    return any(
        isinstance(item, ast.Constant)
        and isinstance(item.value, str)
        and item.value.lower().endswith(".py")
        for item in ast.walk(node)
    )


def scan_source(path: str, source: str) -> list[Violation]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [
            Violation(
                path, exc.lineno or 0, "ARCH000", "Python syntax error prevents boundary analysis"
            )
        ]

    violations: list[Violation] = []
    runtime_scope = path.replace("\\", "/").startswith("scripts/")
    tab_scope = path.replace("\\", "/").startswith("scripts/tabs/")
    venv_python_variables = _python_interpreter_variables(tree)
    python_script_variables = _python_script_variables(tree)
    assigned_values = _assigned_values(tree)

    for node in ast.walk(tree):
        if runtime_scope and isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORT_PREFIXES:
                    violations.append(
                        Violation(
                            path,
                            node.lineno,
                            "ARCH001",
                            f"direct import of external app namespace: {alias.name}",
                        )
                    )
        elif runtime_scope and isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in FORBIDDEN_IMPORT_PREFIXES:
                violations.append(
                    Violation(
                        path,
                        node.lineno,
                        "ARCH001",
                        f"direct import of external app namespace: {node.module}",
                    )
                )

        if tab_scope and isinstance(node, ast.Attribute) and _name(node) == "sys.executable":
            violations.append(
                Violation(
                    path,
                    node.lineno,
                    "ARCH002",
                    "runtime tab depends on sys.executable; launch a packaged exe or use an API instead",
                )
            )

        if isinstance(node, ast.Call):
            called = _name(node.func)
            if called == "shutil.which" and node.args and isinstance(node.args[0], ast.Constant):
                value = str(node.args[0].value).lower()
                if value in PYTHON_COMMANDS:
                    violations.append(
                        Violation(
                            path,
                            node.lineno,
                            "ARCH003",
                            f"PATH Python discovery is forbidden: {value}",
                        )
                    )

            if called in SUBPROCESS_CALLS and node.args:
                command = node.args[0]
                command_elements = _command_elements(command, assigned_values)
                if (
                    len(command_elements) > 1
                    and _is_python_interpreter_expression(
                        command_elements[0], venv_python_variables
                    )
                    and _is_python_script_expression(
                        command_elements[1], python_script_variables
                    )
                ):
                    violations.append(
                        Violation(
                            path,
                            node.lineno,
                            "ARCH005",
                            "venv Python must not directly launch a backend .py script; use a packaged executable or API",
                        )
                    )
                if isinstance(command, (ast.List, ast.Tuple)) and command.elts:
                    first = command.elts[0]
                    if (
                        isinstance(first, ast.Constant)
                        and str(first.value).lower() in PYTHON_COMMANDS
                    ):
                        violations.append(
                            Violation(
                                path,
                                node.lineno,
                                "ARCH003",
                                f"PATH Python subprocess is forbidden: {first.value}",
                            )
                        )
                    if _name(first) == "sys.executable":
                        violations.append(
                            Violation(
                                path,
                                node.lineno,
                                "ARCH004",
                                "sys.executable must not launch another app/script",
                            )
                        )

    return violations


def load_baseline(path: Path) -> dict[tuple[str, str], tuple[int, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[tuple[str, str], tuple[int, str]] = {}
    for item in data.get("allow", []):
        result[(item["path"], item["rule"])] = (int(item["max_count"]), item["reason"])
    return result


def scan_repository(
    root: Path, baseline_path: Path | None = None
) -> tuple[list[Violation], list[str]]:
    baseline = load_baseline(
        baseline_path or root / "tools/architecture/app_boundary_baseline.json"
    )
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Enforce API-only boundaries between packaged apps/services."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    baseline = (
        args.baseline.resolve()
        if args.baseline
        else root / "tools/architecture/app_boundary_baseline.json"
    )
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
