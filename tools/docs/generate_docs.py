"""Generate or verify code-derived project documentation."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

try:
    from .generate_class_diagram import render_class_diagram
except ImportError:
    from generate_class_diagram import render_class_diagram


# {
#   責務: [
#     GeneratedDocument: generated documentのpath/content pairを保持する
#   ],
#   処理: [
#     1: 宣言に対応する状態を保持する,
#     2: 主要methodがその状態を構築・検査・変換・出力する,
#   ],
#   フィールド: [
#     path: Path field stored by this declaration,
#     content: str field stored by this declaration,
#   ],
#   引数: [],
#   戻り値: [
#     GeneratedDocument: instance of this class,
#   ],
# }
@dataclass(frozen=True)
class GeneratedDocument:
    path: Path
    content: str


# {
#   責務: [
#     project_root: tools module位置からrepository rootを解決する
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: Path as described by the annotated return type,
#   ],
# }
def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


# {
#   責務: [
#     load_config: documentation generator config JSONを読み込む
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     path: 検査または変換するfile path (Path),
#   ],
#   戻り値: [
#     result: dict as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


# {
#   責務: [
#     build_documents: configurationに従ってgenerated documentsをrenderする
#   ],
#   処理: [
#     1: 引数と既存stateを検証して処理結果を算出する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     root: repository or migration root (Path),
#     config: parsed config mapping (dict),
#   ],
#   戻り値: [
#     result: list[GeneratedDocument] as described by the annotated return type,
#   ],
#   エラー: [
#     ValueError: invalid input, unsafe path, or command failure,
#   ],
# }
def build_documents(root: Path, config: dict) -> list[GeneratedDocument]:
    documents: list[GeneratedDocument] = []
    source_roots = [root / item for item in config.get("source_roots", [])]
    outputs = config.get("outputs", {})
    docs = config.get("docs", {})

    if docs.get("class_diagram", False):
        output = outputs.get("class_diagram")
        if not output:
            raise ValueError("outputs.class_diagram is required when class_diagram is enabled")
        documents.append(GeneratedDocument(root / output, render_class_diagram(source_roots)))

    return documents


# {
#   責務: [
#     write_documents: generated document contentsをtarget pathsへ書き出す
#   ],
#   処理: [
#     1: 計画したfilesystem output/updateを適用する,
#     2: validated resultをcallerへ返す,
#   ],
#   引数: [
#     documents: documents value used by write_documents (list[GeneratedDocument]),
#   ],
#   戻り値: [
#     result: None as described by the annotated return type,
#   ],
#   副作用: [
#     指定されたfilesystem pathsを作成、更新、移動、置換、または削除する,
#   ],
# }
def write_documents(documents: list[GeneratedDocument]) -> None:
    for document in documents:
        document.path.parent.mkdir(parents=True, exist_ok=True)
        document.path.write_text(document.content, encoding="utf-8")


# {
#   責務: [
#     stale_documents: current outputとgenerated contentを比較してoutdated pathsを返す
#   ],
#   処理: [
#     1: input path / repository stateを確認する,
#     2: source/config/metadataを読み込んで解析する,
#     3: validated resultをcallerへ返す,
#   ],
#   引数: [
#     documents: documents value used by stale_documents (list[GeneratedDocument]),
#   ],
#   戻り値: [
#     result: list[Path] as described by the annotated return type,
#   ],
#   副作用: [
#     local source/config/build filesを読み込み、filesystem stateを検査する,
#   ],
# }
def stale_documents(documents: list[GeneratedDocument]) -> list[Path]:
    return [
        document.path
        for document in documents
        if not document.path.exists() or document.path.read_text(encoding="utf-8") != document.content
    ]


# {
#   責務: [
#     main: documentation configからgenerated docsを生成するか、--checkでstalenessを報告する
#   ],
#   処理: [
#     1: CLI argumentsをparseする (--check, --config),
#     2: documentation configからgenerated docsを生成するか、--checkでstalenessを報告する,
#     3: resultとexit statusを返す,
#   ],
#   引数: [],
#   戻り値: [
#     result: int as described by the annotated return type,
#   ],
#   副作用: [
#     config/source/generated docsを読み込む,
#     --check未指定時はgenerated documentation filesを作成・更新する,
#     check結果とstale pathsを標準出力へ表示する,
#   ],
# }
def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or verify code-derived documentation")
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    parser.add_argument("--config", type=Path, help="configuration path relative to repository root")
    args = parser.parse_args()

    root = project_root()
    config_path = args.config or Path("tools/docs/config.json")
    if not config_path.is_absolute():
        config_path = root / config_path

    documents = build_documents(root, load_config(config_path))
    if args.check:
        stale = stale_documents(documents)
        if stale:
            for path in stale:
                print(f"[STALE] {path.relative_to(root)}")
            return 1
        print(f"[OK] {len(documents)} generated document(s) are current")
        return 0

    write_documents(documents)
    print(f"[OK] generated {len(documents)} document(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
