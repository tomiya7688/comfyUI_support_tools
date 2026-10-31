"""Generate a lightweight Mermaid class diagram from Python source."""

from __future__ import annotations

import ast
import os
from pathlib import Path


class ClassCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes: list[tuple[str, list[str], list[str]]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [self._name(base) for base in node.bases if self._name(base)]
        methods = [
            item.name
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.classes.append((node.name, bases, methods))
        self.generic_visit(node)

    @staticmethod
    def _name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts: list[str] = []
            current: ast.AST | None = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                return ".".join(reversed(parts))
        return ""


# {
#   責務: [should_skip_directory: class diagram生成で仮想環境とcache directoryを除外する]
#   処理: [1: directory名を正規化する, 2: Python環境またはcacheに一致するか返す]
#   引数: [name: directory name]
#   戻り値: [should_skip: traversalから除外する場合true]
# }
def should_skip_directory(name: str) -> bool:
    normalized = name.casefold()
    return (
        normalized == "__pycache__"
        or normalized == "venv"
        or normalized.startswith((".venv", "venv-", "venv.", "venv_"))
    )


# {
#   責務: [is_virtual_environment: directoryがPython仮想環境か判定する]
#   処理: [1: 名前規則を確認する, 2: pyvenv.cfgの存在を確認する]
#   引数: [directory: 確認するdirectory]
#   戻り値: [is_venv: 仮想環境ならtrue]
# }
def is_virtual_environment(directory: Path) -> bool:
    return should_skip_directory(directory.name) or (directory / "pyvenv.cfg").is_file()


# {
#   責務: [iter_python_files: class diagram対象のproject-owned Python fileを列挙する]
#   処理: [1: source treeを走査する, 2: venv/cache directoryをpruneする, 3: Python fileを並べて返す]
#   引数: [root: source treeのroot directory]
#   戻り値: [python_files: source tree内のPython file一覧]
# }
def iter_python_files(root: Path) -> list[Path]:
    if is_virtual_environment(root):
        return []
    python_files: list[Path] = []
    for directory, child_directories, filenames in os.walk(root):
        child_directories[:] = [
            name for name in child_directories if not is_virtual_environment(Path(directory) / name)
        ]
        python_files.extend(
            Path(directory) / filename for filename in filenames if filename.endswith(".py")
        )
    return sorted(python_files)


def render_class_diagram(source_roots: list[Path]) -> str:
    lines = ["classDiagram"]
    seen_relations: set[tuple[str, str]] = set()

    for source_root in source_roots:
        if not source_root.exists():
            continue
        for path in iter_python_files(source_root):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                continue

            collector = ClassCollector()
            collector.visit(tree)
            for class_name, bases, methods in collector.classes:
                lines.append(f"    class {class_name} {{")
                for method in methods:
                    lines.append(f"        +{method}()")
                lines.append("    }")
                for base in bases:
                    relation = (base, class_name)
                    if relation not in seen_relations:
                        seen_relations.add(relation)
                        lines.append(f"    {base} <|-- {class_name}")

    return "\n".join(lines) + "\n"
