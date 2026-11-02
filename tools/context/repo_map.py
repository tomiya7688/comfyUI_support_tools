from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path


# {
#   責務: [
#     SymbolInfo: source declarationのname、kind、lineを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     name: str field stored by this declaration,
#     kind: str field stored by this declaration,
#     line: int field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     SymbolInfo: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class SymbolInfo:
    name: str
    kind: str
    line: int


# {
#   責務: [
#     FileInfo: repository-relative file、imports、symbolsを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     path: str field stored by this declaration,
#     imports: list[str] field stored by this declaration,
#     symbols: list[SymbolInfo] field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     FileInfo: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class FileInfo:
    path: str
    imports: list[str]
    symbols: list[SymbolInfo]


# {
#   責務: [
#     collect_imports: ASTからimport target namesを収集する
#   ],
#   処理: [
#     1: 対象 declarations/filesystem entriesを走査する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     tree: parsed Python AST (ast.AST),
#   ],
#   戻り値: [
#     result: list[str] as described by the annotated return type,
#   ],
# }
def collect_imports(tree: ast.AST) -> list[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.add(("." * node.level) + module)
    return sorted(imports)


# {
#   責務: [
#     collect_symbols: ASTからclass/function declarationsを位置順に収集する
#   ],
#   処理: [
#     1: 対象 declarations/filesystem entriesを走査する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     tree: parsed Python AST (ast.AST),
#   ],
#   戻り値: [
#     result: list[SymbolInfo] as described by the annotated return type,
#   ],
# }
def collect_symbols(tree: ast.AST) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(SymbolInfo(node.name, "function", node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(SymbolInfo(node.name, "class", node.lineno))
    return sorted(symbols, key=lambda item: (item.line, item.name))


# {
#   責務: [
#     inspect_file: Python fileをparseし、FileInfoを構築する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: source/config/metadataを読み込んで解析する,
#     3: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path: 検査または変換するfile path (Path),
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: FileInfo | None as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
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


# {
#   責務: [
#     build_repo_map: 対象 source rootsを走査してrepository map documentを構築する
#   ],
#   処理: [
#     1: 対象 declarations/filesystem entriesを走査する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#   ],
#   戻り値: [
#     result: dict[str, object] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
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


# {
#   責務: [
#     write_repo_map: repository map JSONをoutput pathへ書き出す
#   ],
#   処理: [
#     1: 計画したfilesystem output/updateを適用する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     data: repository map JSON data (dict[str, object]),
#     output: result output directory (Path),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     指定されたfilesystem pathsを作成、更新、移動、置換、または削除する,
#   ],
# }
def write_repo_map(data: dict[str, object], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# {
#   責務: [
#     main: configured source rootsからrepository mapを作成してoutputへ書き出す
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--root, --output, --stdout),
#     2: configured source rootsからrepository mapを作成してoutputへ書き出す,
#     3: resultとexit statusを返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     source filesを読み込み、repository map JSONをoutput pathへ書き込む,
#   ],
# }
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
