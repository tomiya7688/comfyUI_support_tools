from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


FORBIDDEN_IMPORT_PREFIXES = ("nuno", "modules", "webui")
PYTHON_COMMANDS = {"python", "python3", "py", "python.exe", "pythonw.exe"}


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


def scan_source(path: str, source: str) -> list[Violation]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [Violation(path, exc.lineno or 0, "ARCH000", "Python syntax error prevents boundary analysis")]

    violations: list[Violation] = []
    runtime_scope = path.replace("\\", "/").startswith("scripts/")
    tab_scope = path.replace("\\", "/").startswith("scripts/tabs/")

    # Track simple local assignments so helper-resolved interpreters are treated
    # like literal Python commands at subprocess boundaries.
    python_values: set[str] = set()
    script_values: set[str] = set()
    command_values: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        for name in names:
            command_values[name] = value
        if not names:
            continue
        if isinstance(value, ast.Call) and _name(value.func).endswith("venv_python"):
            python_values.update(names)
        elif any(isinstance(part, ast.Attribute) and part.attr.endswith("script_name") for part in ast.walk(value)):
            script_values.update(names)
        elif isinstance(value, ast.BinOp) and any(
            isinstance(part, ast.Constant) and str(part.value).lower().endswith(".py") for part in ast.walk(value)
        ):
            script_values.update(names)
        elif "python" in ast.unparse(value).lower():
            if isinstance(value, ast.Call) and _name(value.func) == "Path" or isinstance(value, ast.BinOp):
                python_values.update(names)
        elif isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div):
            if isinstance(value.right, ast.Constant) and str(value.right.value).lower().endswith(".py"):
                script_values.update(names)

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
                if isinstance(command, ast.Name):
                    command = command_values.get(command.id, command)
                if isinstance(command, (ast.List, ast.Tuple)) and command.elts:
                    first = command.elts[0]
                    if isinstance(first, ast.Constant) and str(first.value).lower() in PYTHON_COMMANDS:
                        violations.append(Violation(path, node.lineno, "ARCH003", f"PATH Python subprocess is forbidden: {first.value}"))
                    if _name(first) == "sys.executable":
                        violations.append(Violation(path, node.lineno, "ARCH004", "sys.executable must not launch another app/script"))
                    first_value = first.args[0] if isinstance(first, ast.Call) and _name(first.func) == "str" and first.args else first
                    if isinstance(first_value, ast.Call) and _name(first_value.func) == "packaged_executable":
                        continue
                    if isinstance(first_value, ast.Name) and first_value.id in python_values:
                        if len(command.elts) > 1:
                            second = command.elts[1]
                            if isinstance(second, ast.Call) and _name(second.func) == "str" and second.args:
                                second = second.args[0]
                            if isinstance(second, ast.Name) and second.id in script_values:
                                violations.append(Violation(path, node.lineno, "ARCH005", "venv Python must not launch an external backend script"))
                            elif isinstance(second, ast.Call) and _name(second.func) == "str" and second.args and isinstance(second.args[0], ast.Name) and second.args[0].id in script_values:
                                violations.append(Violation(path, node.lineno, "ARCH005", "venv Python must not launch an external backend script"))
                            elif isinstance(second, ast.Constant) and str(second.value).lower().endswith(".py"):
                                violations.append(Violation(path, node.lineno, "ARCH005", "venv Python must not launch an external backend script"))

    return violations


def load_baseline(path: Path) -> dict[tuple[str, str], tuple[int, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[tuple[str, str], tuple[int, str]] = {}
    for item in data.get("allow", []):
        result[(item["path"], item["rule"])] = (int(item["max_count"]), item["reason"])
    return result


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
