from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


LAYER_ORDER = {"ui": 0, "process": 1, "data": 2}
ROLES = {"commander", "messenger", "processing"}
DIRECT_WORK_CALL_PREFIXES = (
    "subprocess.",
    "requests.",
    "urllib.",
    "sqlite3.",
    "socket.",
    "shutil.",
)
DIRECT_WORK_CALL_NAMES = {
    "open",
    "eval",
    "exec",
}
DIRECT_WORK_METHODS = {
    "read_text",
    "write_text",
    "read_bytes",
    "write_bytes",
    "open",
    "unlink",
    "mkdir",
    "rmdir",
    "rename",
    "replace",
}


@dataclass(frozen=True)
class ModuleRole:
    application: str
    layer: str
    role: str


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    message: str


def classify(path: str) -> ModuleRole | None:
    parts = Path(path).as_posix().split("/")
    try:
        app_index = parts.index("applications")
    except ValueError:
        return None
    if app_index + 2 >= len(parts):
        return None

    application = parts[app_index + 1]
    layer = parts[app_index + 2]
    if layer not in LAYER_ORDER:
        return None

    role = ""
    if app_index + 3 < len(parts) and parts[app_index + 3] in ROLES:
        role = parts[app_index + 3]
    return ModuleRole(application, layer, role)


def _name(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _import_target(module: str) -> tuple[str, str, str] | None:
    parts = module.split(".")
    if "applications" not in parts:
        return None
    index = parts.index("applications")
    if index + 2 >= len(parts):
        return None
    app = parts[index + 1]
    layer = parts[index + 2]
    role = parts[index + 3] if index + 3 < len(parts) and parts[index + 3] in ROLES else ""
    if layer not in LAYER_ORDER:
        return None
    return app, layer, role


def _allowed_cross_layer(source: ModuleRole, target_layer: str, target_role: str) -> bool:
    if source.layer == target_layer:
        return True
    if abs(LAYER_ORDER[source.layer] - LAYER_ORDER[target_layer]) != 1:
        return False
    if source.role != "messenger":
        return False
    return target_role in {"messenger", "commander"}


def scan_source(path: str, source: str) -> list[Finding]:
    role = classify(path)
    if role is None:
        return []

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return [Finding("UPD001", path, exc.lineno or 0, "syntax error prevents UPD analysis")]

    findings: list[Finding] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)

        for module in modules:
            target = _import_target(module)
            if target is None:
                continue
            target_app, target_layer, target_role = target
            if target_app != role.application:
                findings.append(
                    Finding(
                        "UPD102",
                        path,
                        node.lineno,
                        f"direct dependency on another Application internal module: {module}",
                    )
                )
                continue
            if not _allowed_cross_layer(role, target_layer, target_role):
                findings.append(
                    Finding(
                        "UPD101",
                        path,
                        node.lineno,
                        f"{role.layer}/{role.role or 'module'} must not directly import "
                        f"{target_layer}/{target_role or 'module'}: {module}",
                    )
                )

        if role.role == "commander":
            if isinstance(node, (ast.For, ast.While, ast.AsyncFor)):
                findings.append(
                    Finding("UPD201", path, node.lineno, "Commander contains a loop; move work to Processing")
                )
            elif isinstance(node, ast.BinOp):
                findings.append(
                    Finding("UPD202", path, node.lineno, "Commander contains a calculation; move work to Processing")
                )
            elif isinstance(node, ast.Call):
                called = _name(node.func)
                leaf = called.rsplit(".", 1)[-1]
                if (
                    called in DIRECT_WORK_CALL_NAMES
                    or called.startswith(DIRECT_WORK_CALL_PREFIXES)
                    or leaf in DIRECT_WORK_METHODS
                ):
                    findings.append(
                        Finding(
                            "UPD203",
                            path,
                            node.lineno,
                            f"Commander performs direct work/API call: {called or leaf}",
                        )
                    )
    return findings


def scan_repository(root: Path) -> list[Finding]:
    source_root = root / "src" / "comfyui_support_tools" / "applications"
    if not source_root.exists():
        return []
    findings: list[Finding] = []
    for path in sorted(source_root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        findings.extend(scan_source(rel, path.read_text(encoding="utf-8")))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check new src/applications code against the UPD Commander boundaries."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)

    findings = scan_repository(args.root.resolve())
    for finding in findings:
        print(f"E {finding.rule} {finding.path}:{finding.line} {finding.message}")
    if findings:
        print(f"FAIL e={len(findings)}")
        return 1
    print("OK: UPD application boundaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
