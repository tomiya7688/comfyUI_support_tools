from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class SymbolInfo:
    name: str
    kind: str
    line: int


@dataclass(frozen=True)
class FileInfo:
    path: str
    imports: list[str]
    symbols: list[SymbolInfo]


def collect_imports(tree: ast.AST) -> list[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.add(("." * node.level) + module)
    return sorted(imports)


def collect_symbols(tree: ast.AST) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(SymbolInfo(node.name, "function", node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(SymbolInfo(node.name, "class", node.lineno))
    return sorted(symbols, key=lambda item: (item.line, item.name))


def inspect_file(path: Path, root: Path) -> FileInfo | None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None
    return FileInfo(
        path=path.relative_to(root).as_posix(),
        imports=collect_imports(tree),
        symbols=collect_symbols(tree),
    )


def build_repo_map(root: Path) -> dict[str, object]:
    files: list[FileInfo] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        info = inspect_file(path, root)
        if info is not None:
            files.append(info)
    return {
        "version": 1,
        "file_count": len(files),
        "files": [
            {
                **asdict(info),
                "symbols": [asdict(symbol) for symbol in info.symbols],
            }
            for info in files
        ],
    }


def write_repo_map(data: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a compact Python repository map.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default=".codex/repo_map.json")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    data = build_repo_map(Path(args.root).resolve())
    if args.stdout:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    else:
        write_repo_map(data, Path(args.output))
        print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
