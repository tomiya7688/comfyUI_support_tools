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


# {
#   責務: [
#     ModuleRole: Python moduleのUPD layerとroleを表す
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     application: str field stored by this declaration,
#     layer: str field stored by this declaration,
#     role: str field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     ModuleRole: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class ModuleRole:
    application: str
    layer: str
    role: str


# {
#   責務: [
#     Finding: UPD dependency scanで検出した違反を保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     rule: str field stored by this declaration,
#     path: str field stored by this declaration,
#     line: int field stored by this declaration,
#     message: str field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     Finding: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    message: str


# {
#   責務: [
#     classify: repository pathからmoduleのUPD layer / roleを分類する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path: 検査または変換するfile path (str),
#   ],
#   戻り値: [
#     result: ModuleRole | None as described by the annotated return type,
#   ],
# }
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
#     _import_target: import名からtarget layerとmodule roleを解決する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     module: Python module path (str),
#   ],
#   戻り値: [
#     result: tuple[str, str, str] | None as described by the annotated return type,
#   ],
# }
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


# {
#   責務: [
#     _allowed_cross_layer: UPD layer間のimportが許可されるかを判定する
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     source: legacy path root (ModuleRole),
#     target_layer: target module layer (str),
#     target_role: target module role (str),
#   ],
#   戻り値: [
#     result: bool as described by the annotated return type,
#   ],
# }
def _allowed_cross_layer(source: ModuleRole, target_layer: str, target_role: str) -> bool:
    if source.layer == target_layer:
        return True
    if abs(LAYER_ORDER[source.layer] - LAYER_ORDER[target_layer]) != 1:
        return False
    if source.role != "messenger":
        return False
    return target_role in {"messenger", "commander"}


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
#     result: list[Finding] as described by the annotated return type,
#   ],
# }
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
            elif isinstance(node, ast.BinOp) and not isinstance(node.op, ast.BitOr):
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
#   ],
#   戻り値: [
#     result: list[Finding] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def scan_repository(root: Path) -> list[Finding]:
    source_root = root / "src" / "comfyui_support_tools" / "applications"
    if not source_root.exists():
        return []
    findings: list[Finding] = []
    for path in sorted(source_root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        findings.extend(scan_source(rel, path.read_text(encoding="utf-8")))
    return findings


# {
#   責務: [
#     main: UPD境界check CLIを解析し、module dependency違反を報告して終了statusを返す
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--root),
#     2: UPD境界check CLIを解析し、module dependency違反を報告して終了statusを返す,
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
