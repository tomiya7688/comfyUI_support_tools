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


def _venv_python_variables(tree: ast.AST) -> set[str]:
    """Find variables that hold a venv interpreter, including simple aliases."""
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
            if isinstance(value, ast.Call) and _name(value.func).endswith("venv_python"):
                dependencies = set()
            else:
                dependencies = _names(value)
            if not dependencies.intersection(variables) and not (
                isinstance(value, ast.Call) and _name(value.func).endswith("venv_python")
            ):
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
    venv_python_variables = _venv_python_variables(tree)
    python_script_variables = _python_script_variables(tree)

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
                command_names = _names(command)
                command_text_has_python_script = any(
                    isinstance(item, ast.Constant)
                    and isinstance(item.value, str)
                    and item.value.lower().endswith(".py")
                    for item in ast.walk(command)
                )
                if command_names.intersection(venv_python_variables) and (
                    command_names.intersection(python_script_variables)
                    or command_text_has_python_script
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
