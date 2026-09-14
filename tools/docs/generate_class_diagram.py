"""Generate a lightweight Mermaid class diagram from Python source."""

from __future__ import annotations

import ast
from pathlib import Path


class ClassCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.classes: list[tuple[str, list[str], list[str]]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [self._name(base) for base in node.bases if self._name(base)]
        methods = [item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))]
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


def iter_python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and ".venv" not in path.parts and "venv" not in path.parts
    )


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
