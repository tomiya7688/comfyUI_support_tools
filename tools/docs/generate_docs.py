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


@dataclass(frozen=True)
class GeneratedDocument:
    path: Path
    content: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


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


def write_documents(documents: list[GeneratedDocument]) -> None:
    for document in documents:
        document.path.parent.mkdir(parents=True, exist_ok=True)
        document.path.write_text(document.content, encoding="utf-8")


def stale_documents(documents: list[GeneratedDocument]) -> list[Path]:
    return [
        document.path
        for document in documents
        if not document.path.exists() or document.path.read_text(encoding="utf-8") != document.content
    ]


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
