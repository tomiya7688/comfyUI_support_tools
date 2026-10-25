from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PRODUCT_ROOTS = ("scripts", "src")


# {
# 責務: [ Finding: resource leak gateの検出結果を表す ]
# フィールド: [ rule: rule ID, path: file path, line: 行番号, message: 検出内容 ]
# 処理: []
# }
@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    message: str


# {
# 責務: [ _call_name: ASTのcall targetをdotted nameへ変換する ]
# 処理: [ 1: attribute chainを遡る, 2: nameを連結して返す ]
# 引数: [ node: call target AST ]
# 戻り値: [ name: dotted call name ]
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
# 責務: [ _queue_is_bounded: queue.Queueに正のmaxsize指定があるか判定する ]
# 処理: [ 1: positionalまたはmaxsize keywordを探す, 2: 明示0以下を拒否しその他の指定値をbounded扱いする ]
# 引数: [ node: queue.Queue call ]
# 戻り値: [ bounded: 有限上限指定がある場合true ]
# }
def _queue_is_bounded(node: ast.Call) -> bool:
    bound: ast.AST | None = node.args[0] if node.args else None
    for keyword in node.keywords:
        if keyword.arg == "maxsize":
            bound = keyword.value
            break
    if bound is None:
        return False
    if isinstance(bound, ast.Constant) and isinstance(bound.value, (int, float)):
        return bound.value > 0
    return True


# {
# 責務: [ scan_source: 1つのPython sourceからresource retention危険patternを検出する ]
# 処理: [ 1: ASTをparseする, 2: 無制限Queueとcommunicateを検出する, 3: health monitor内のsleepを検出する ]
# 引数: [ path: repository相対path, source: Python source ]
# 戻り値: [ findings: 検出結果 ]
# }
def scan_source(path: str, source: str) -> list[Finding]:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as error:
        return [Finding("RLG000", path, error.lineno or 0, f"syntax error: {error.msg}")]

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = _call_name(node.func)
            if called == "queue.Queue" and not _queue_is_bounded(node):
                findings.append(
                    Finding(
                        "RLG001",
                        path,
                        node.lineno,
                        "queue.Queue must set a positive maxsize",
                    )
                )
            if isinstance(node.func, ast.Attribute) and node.func.attr == "communicate":
                findings.append(
                    Finding(
                        "RLG002",
                        path,
                        node.lineno,
                        "subprocess communicate() buffers full output; stream or bound output instead",
                    )
                )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lowered = node.name.casefold()
            if "health" in lowered and "check" in lowered:
                for nested in ast.walk(node):
                    if isinstance(nested, ast.Call) and _call_name(nested.func) == "time.sleep":
                        findings.append(
                            Finding(
                                "RLG003",
                                path,
                                nested.lineno,
                                "health monitor must use Event.wait so shutdown wakes it immediately",
                            )
                        )
    return findings


# {
# 責務: [ scan_repository: product Python source全体をresource leak ruleで検査する ]
# 処理: [ 1: scriptsとsrc配下を列挙する, 2: Python sourceをscanする, 3: path順へ整列する ]
# 引数: [ root: repository root ]
# 戻り値: [ findings: repository全体の検出結果 ]
# }
def scan_repository(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for product_root in PRODUCT_ROOTS:
        base = root / product_root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            relative = path.relative_to(root).as_posix()
            findings.extend(scan_source(relative, path.read_text(encoding="utf-8")))
    return sorted(findings, key=lambda item: (item.path, item.line, item.rule))


# {
# 責務: [ main: resource leak gateをCLIとして実行する ]
# 処理: [ 1: repositoryをscanする, 2: findingを表示する, 3: finding有無をexit codeへ反映する ]
# 引数: []
# 戻り値: [ exit_code: findingがあれば1、なければ0 ]
# }
def main() -> int:
    root = Path(__file__).resolve().parents[2]
    findings = scan_repository(root)
    for finding in findings:
        print(f"{finding.path}:{finding.line}: {finding.rule} {finding.message}")
    if findings:
        print(f"resource leak gate: {len(findings)} finding(s)")
        return 1
    print("resource leak gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
