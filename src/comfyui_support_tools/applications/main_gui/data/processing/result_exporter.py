"""Explicit, bounded result export. No directories are created implicitly."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import uuid

from comfyui_support_tools.shared.contracts.inspector_contracts import ExportSettings, MediaExportRecord

MAX_EXPORT_RECORDS = 60


def _caption(notes, include_style):
    if notes.caption.strip():
        return notes.caption.strip()
    tags = list(notes.content_tags) + list(notes.character_tags) + list(notes.copyright_tags)
    if include_style:
        tags.extend(notes.style_tags)
    return ", ".join(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))


def _metadata(record):
    item, notes = record.item, record.notes
    return {
        "schema_version": 1,
        "source": {
            "id": item.id,
            "path": item.path,
            "name": item.name,
            "kind": item.kind,
            "collection": item.collection,
            "size": item.size,
            "modified_ns": item.modified_ns,
        },
        "analysis": {
            "content_tags": list(notes.content_tags),
            "character_tags": list(notes.character_tags),
            "copyright_tags": list(notes.copyright_tags),
            "rating": notes.rating,
            "style_tags": list(notes.style_tags),
            "caption": notes.caption,
            "tagger_backend": notes.tagger_backend,
            "tagger_model": notes.tagger_model,
            "content_scores": [asdict(value) for value in notes.content_scores],
            "character_scores": [asdict(value) for value in notes.character_scores],
            "rating_scores": [asdict(value) for value in notes.rating_scores],
        },
        "notes": {
            "prompt": notes.prompt,
            "negative_prompt": notes.negative_prompt,
            "character": notes.character,
            "dataset": notes.dataset,
        },
    }


def _source_ok(record):
    path = Path(record.item.path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError(f"Sourceがありません / linkは対象外です: {record.item.name}")
    stat = path.stat()
    if (stat.st_size, stat.st_mtime_ns) != (record.item.size, record.item.modified_ns):
        raise ValueError(f"Sourceが変更されています。Browserを再読込してください: {record.item.name}")


def _write(path, content, overwrite):
    if path.is_symlink():
        raise ValueError(f"symlinkへの出力は拒否しました: {path}")
    if not path.parent.is_dir():
        raise ValueError(f"出力先フォルダがありません: {path.parent}")
    if not overwrite:
        with path.open("x", encoding="utf-8", newline="\n") as destination:
            destination.write(content)
        return
    temporary = path.with_name(f".{path.name}.kadoka-{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def export_records(records, settings: ExportSettings, progress=None):
    records = tuple(records)
    if not records or len(records) > MAX_EXPORT_RECORDS:
        raise ValueError("Exportは画像1〜60件を選択してください")
    if not (settings.caption_sidecar or settings.metadata_sidecar or settings.batch_txt_path):
        raise ValueError("少なくとも1つの出力形式を選択してください")
    for record in records:
        if record.item.kind != "image":
            raise ValueError("Exportは画像のみ対応です")
        _source_ok(record)

    planned = []
    batch_lines = []
    for record in records:
        source = Path(record.item.path)
        caption = _caption(record.notes, settings.include_style_in_caption)
        if settings.caption_sidecar:
            planned.append((source.with_suffix(".txt"), caption + "\n"))
        if settings.metadata_sidecar:
            planned.append((
                source.with_suffix(source.suffix + ".kadoka.json"),
                json.dumps(_metadata(record), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            ))
        if settings.batch_txt_path:
            batch_lines.append(f"{record.item.path}\t{caption}")

    if settings.batch_txt_path:
        batch = Path(settings.batch_txt_path).expanduser().absolute()
        if batch.suffix.lower() != ".txt":
            raise ValueError("Batch TXTは .txt を指定してください")
        planned.append((batch, "\n".join(batch_lines) + "\n"))

    normalized = [path.absolute() for path, _ in planned]
    if len(set(map(str, normalized))) != len(normalized):
        raise ValueError("出力先が重複しています")
    source_paths = {str(Path(record.item.path).absolute()) for record in records}
    if any(str(path) in source_paths for path in normalized):
        raise ValueError("元画像を出力先として指定できません")
    for path in normalized:
        if path.exists() and not settings.overwrite:
            raise FileExistsError(f"既存ファイルがあります（overwrite OFF）: {path}")
        if path.is_symlink():
            raise ValueError(f"symlinkへの出力は拒否しました: {path}")

    total = len(planned)
    written = []
    for index, ((_, content), path) in enumerate(zip(planned, normalized), 1):
        _write(path, content, settings.overwrite)
        written.append(str(path))
        if progress:
            progress(index, total, path.name)
    return tuple(written)
