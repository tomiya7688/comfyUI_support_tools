"""Explicit, bounded result export. No directories are created implicitly."""

from dataclasses import asdict
import json
from pathlib import Path
import tempfile

from comfyui_support_tools.shared.contracts.inspector_contracts import (
    ExportSettings,
    MediaExportRecord,
)
from comfyui_support_tools.shared.output_artifact import ConflictPolicy, atomic_write_bytes
from comfyui_support_tools.shared.transparency_contracts import (
    MediaClassification,
    ModelDisclosure,
    PromptDisclosure,
    ProvenanceAction,
    ProvenanceRecord,
    TransparencySettings,
    VerificationFailurePolicy,
    WorkflowDisclosure,
)
from comfyui_support_tools.shared.c2pa_adapter import C2paAdapter, PemFileSignerProvider
from comfyui_support_tools.shared.transparency_sidecar import (
    build_transparency_sidecar,
    serialize_transparency_sidecar,
    sha256_bytes,
    sha256_file,
)
from comfyui_support_tools.shared.png_transparency_metadata import (
    create_png_transparency_copy,
    verify_png_transparency,
)

MAX_EXPORT_RECORDS = 60
MAX_WORKFLOW_DISCLOSURE_BYTES = 8 * 1024 * 1024


def _caption(notes, include_style):
    if notes.caption.strip():
        return notes.caption.strip()
    tags = list(notes.content_tags) + list(notes.character_tags) + list(notes.copyright_tags)
    if include_style:
        tags.extend(notes.style_tags)
    return ", ".join(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))


def _metadata(record, *, redact_prompts=False, redact_models=False):
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
            "tagger_backend": None if redact_models else notes.tagger_backend,
            "tagger_model": None if redact_models else notes.tagger_model,
            "content_scores": [asdict(value) for value in notes.content_scores],
            "character_scores": [asdict(value) for value in notes.character_scores],
            "rating_scores": [asdict(value) for value in notes.rating_scores],
        },
        "notes": {
            "prompt": None if redact_prompts else notes.prompt,
            "negative_prompt": None if redact_prompts else notes.negative_prompt,
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
        raise ValueError(
            f"Sourceが変更されています。Browserを再読込してください: {record.item.name}"
        )


def _write(path, content, overwrite):
    validator = lambda staged: (
        json.loads(staged.read_text(encoding="utf-8")) if path.suffix.lower() == ".json" else None
    )
    atomic_write_bytes(
        path,
        content.encode("utf-8") if isinstance(content, str) else content,
        policy=ConflictPolicy.OVERWRITE if overwrite else ConflictPolicy.FAIL,
        validator=validator,
    )


def export_records(records, settings: ExportSettings, progress=None):
    records = tuple(records)
    if not records or len(records) > MAX_EXPORT_RECORDS:
        raise ValueError("Exportは画像1〜60件を選択してください")
    if not (
        settings.caption_sidecar
        or settings.metadata_sidecar
        or settings.batch_txt_path
        or settings.transparency_assist
        or settings.transparency_c2pa_sign
        or settings.transparency_png_copy
    ):
        raise ValueError("少なくとも1つの出力形式を選択してください")
    if settings.transparency_png_copy and not settings.transparency_assist:
        raise ValueError("PNG埋め込みにはTransparency Assistを有効にしてください")
    if settings.transparency_c2pa_sign and not settings.transparency_assist:
        raise ValueError("C2PA署名にはTransparency Assistを有効にしてください")
    if settings.transparency_assist and not (
        settings.transparency_sidecar
        or settings.transparency_png_copy
        or settings.transparency_c2pa_sign
    ):
        raise ValueError("Transparency Assistの出力形式を1つ以上選択してください")
    if settings.transparency_png_copy and settings.transparency_c2pa_sign:
        raise ValueError("PNG text metadataとC2PA署名を同じcopyへ追加することはできません")
    if settings.transparency_visible_disclosure and not settings.transparency_png_copy:
        raise ValueError("表示ラベルにはPNG別コピーを有効にしてください")
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
            planned.append(
                (
                    source.with_suffix(source.suffix + ".kadoka.json"),
                    json.dumps(
                        _metadata(
                            record,
                            redact_prompts=settings.transparency_assist,
                            redact_models=settings.transparency_assist,
                        ),
                        ensure_ascii=False,
                        indent=2,
                        allow_nan=False,
                    )
                    + "\n",
                )
            )
        if settings.transparency_assist:
            classification = MediaClassification(settings.transparency_classification)
            prompt_level = PromptDisclosure(settings.transparency_prompt_disclosure)
            model_level = ModelDisclosure(settings.transparency_model_disclosure)
            workflow_level = WorkflowDisclosure(settings.transparency_workflow_disclosure)
            if prompt_level is PromptDisclosure.SANITIZED_SUMMARY and not settings.transparency_prompt_summary.strip():
                raise ValueError("sanitized summary開示には要約を入力してください")
            if model_level is ModelDisclosure.FAMILY and not settings.transparency_model_family.strip():
                raise ValueError("Model family開示にはfamily名を入力してください")
            if model_level in {ModelDisclosure.MODEL_ID, ModelDisclosure.MODEL_ID_AND_VERSION} and not settings.transparency_model_id.strip():
                raise ValueError("Model ID開示にはIDを入力してください")
            if (
                model_level is ModelDisclosure.MODEL_ID_AND_VERSION
                and not settings.transparency_model_version.strip()
                and not settings.transparency_model_hash.strip()
            ):
                raise ValueError("Model ID + version/hash開示にはversionまたはSHA256を入力してください")
            if workflow_level is WorkflowDisclosure.ID and not settings.transparency_workflow_id.strip():
                raise ValueError("Workflow ID開示にはIDを入力してください")
            workflow_json = None
            workflow_file = settings.transparency_workflow_json_path.strip()
            if workflow_level in {WorkflowDisclosure.HASH, WorkflowDisclosure.FULL} and workflow_file:
                workflow_path = Path(workflow_file).expanduser()
                if workflow_path.is_symlink() or not workflow_path.is_file():
                    raise ValueError("Workflow JSONはsymlinkでないregular fileを指定してください")
                if workflow_path.stat().st_size > MAX_WORKFLOW_DISCLOSURE_BYTES:
                    raise ValueError("Workflow JSONは8 MiB以下にしてください")
                workflow_json = json.loads(workflow_path.read_text(encoding="utf-8"))
                if not isinstance(workflow_json, dict):
                    raise ValueError("Workflow JSONのrootはobjectである必要があります")
            if workflow_level is WorkflowDisclosure.FULL and workflow_json is None:
                raise ValueError("Workflow全文開示にはWorkflow JSONを指定してください")
            if workflow_level is WorkflowDisclosure.HASH and workflow_json is None:
                raise ValueError("Workflow hash開示にはWorkflow JSONを指定してください")
            visible_label = {
                MediaClassification.GENERATED: "AI-generated",
                MediaClassification.AI_MODIFIED: "AI-assisted",
            }.get(classification)
            transparency_settings = TransparencySettings(
                enabled=True,
                write_sidecar=settings.transparency_sidecar,
                sign_c2pa=settings.transparency_c2pa_sign,
                prompt_disclosure=prompt_level,
                model_disclosure=model_level,
                workflow_disclosure=workflow_level,
                visible_disclosure=settings.transparency_visible_disclosure,
                visible_disclosure_label=visible_label,
                deepfake_disclosure_assist=settings.transparency_deepfake_assist,
                verification_failure_policy=VerificationFailurePolicy(
                    settings.c2pa_verification_failure_policy
                ),
            )
            transparency_record = ProvenanceRecord(
                classification=classification,
                prompt=record.notes.prompt,
                sanitized_prompt_summary=settings.transparency_prompt_summary.strip() or None,
                model_family=settings.transparency_model_family.strip() or None,
                model_id=settings.transparency_model_id.strip() or None,
                model_version=settings.transparency_model_version.strip() or None,
                model_hash=settings.transparency_model_hash.strip().lower() or None,
                workflow_id=settings.transparency_workflow_id.strip() or None,
                workflow_json=workflow_json,
                deepfake_disclosure_applicable=settings.transparency_deepfake_applicable,
                represents_real_person_place_or_event=(
                    settings.transparency_real_person_place_event
                ),
                user_overrides=(
                    (f"classification:{classification.value}",)
                    if classification is not MediaClassification.UNKNOWN
                    else ()
                ),
                actions=(ProvenanceAction(
                    operation="metadata_export",
                    ai_involvement=False,
                    user_oversight="human_reviewed",
                ),),
            )
            embed_bytes = None
            c2pa_status = "not_requested"
            if settings.transparency_c2pa_sign:
                if classification is MediaClassification.UNKNOWN:
                    raise ValueError("C2PA署名には明示的な技術分類が必要です")
                if not settings.c2pa_certificate_path or not settings.c2pa_private_key_path:
                    raise ValueError("C2PA署名にはPEM証明書と秘密鍵を指定してください")
                signer = PemFileSignerProvider(
                    settings.c2pa_certificate_path,
                    settings.c2pa_private_key_path,
                    timestamp_authority_url=(settings.c2pa_timestamp_authority_url or None),
                )
                signed_copy = source.with_name(
                    f"{source.stem}.transparency.c2pa{source.suffix}"
                )
                with tempfile.TemporaryDirectory(
                    prefix="c2pa-stage-", dir=source.parent
                ) as staging:
                    staged_output = Path(staging) / f"signed{source.suffix}"
                    report = C2paAdapter().sign(
                        source,
                        staged_output,
                        transparency_record,
                        signer,
                        transparency_settings,
                    )
                    embed_bytes = staged_output.read_bytes()
                    c2pa_status = report.to_dict()
                planned.append((signed_copy, embed_bytes))
            if settings.transparency_png_copy:
                embed_payload = build_transparency_sidecar(
                    transparency_record,
                    transparency_settings,
                    output_sha256="",
                    c2pa_manifest_status="not_requested",
                )
                embed_payload.pop("output")
                embed_bytes = create_png_transparency_copy(
                    source,
                    embed_payload,
                    visible_disclosure_label=(
                        transparency_settings.visible_disclosure_label
                        if transparency_settings.visible_disclosure
                        else None
                    ),
                )
                if not verify_png_transparency(embed_bytes, embed_payload):
                    raise ValueError("PNG transparency metadata did not survive export verification")
                planned.append(
                    (source.with_name(f"{source.stem}.transparency.png"), embed_bytes)
                )

            payload = build_transparency_sidecar(
                transparency_record,
                transparency_settings,
                output_sha256=sha256_bytes(embed_bytes) if embed_bytes else sha256_file(source),
                c2pa_manifest_status=c2pa_status,
            )
            if settings.transparency_sidecar:
                planned.append(
                    (
                        source.with_suffix(source.suffix + ".transparency.json"),
                        serialize_transparency_sidecar(payload).decode("utf-8"),
                    )
                )
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
