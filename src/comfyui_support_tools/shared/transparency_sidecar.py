"""Privacy-aware sidecar serialization for transparency provenance."""

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from comfyui_support_tools.shared.transparency_contracts import (
    ModelDisclosure,
    PromptDisclosure,
    ProvenanceRecord,
    TransparencySettings,
    WorkflowDisclosure,
    resolve_profile,
)


# {
# 責務: [ sha256_file: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [path]
# 戻り値: [処理結果]
# }
def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# {
# 責務: [ sha256_bytes: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [value]
# 戻り値: [処理結果]
# }
def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


# {
# 責務: [ _canonical_json: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [value]
# 戻り値: [処理結果]
# }
def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


# {
# 責務: [ build_transparency_sidecar: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [record, settings, output_sha256, c2pa_manifest_status]
# 戻り値: [処理結果]
# }
def build_transparency_sidecar(
    record: ProvenanceRecord,
    settings: TransparencySettings,
    *,
    output_sha256: str,
    c2pa_manifest_status: str = "not_requested",
) -> dict[str, Any]:
    """Build a sidecar without disclosing prompts/models/workflows by default."""
    if not settings.enabled:
        raise ValueError("transparency assist is disabled")
    profile = resolve_profile(settings.profile_id)
    if record.content_type not in profile.supported_media:
        raise ValueError(f"profile does not support content type: {record.content_type}")
    if record.model_hash is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", record.model_hash):
        raise ValueError("model hash must be a 64-character SHA-256 hex digest")
    if settings.visible_disclosure:
        expected_label = {
            "generated": "AI-generated",
            "ai_modified": "AI-assisted",
        }.get(record.classification.value)
        if not expected_label or settings.visible_disclosure_label != expected_label:
            raise ValueError(
                "visible disclosure requires an explicit AI classification and its standard label"
            )

    prompt: dict[str, str] = {"level": settings.prompt_disclosure.value}
    if settings.prompt_disclosure is PromptDisclosure.HASH_ONLY and record.prompt is not None:
        prompt["sha256"] = hashlib.sha256(record.prompt.encode("utf-8")).hexdigest()
    elif settings.prompt_disclosure is PromptDisclosure.SANITIZED_SUMMARY:
        if record.sanitized_prompt_summary:
            prompt["summary"] = record.sanitized_prompt_summary
    elif settings.prompt_disclosure is PromptDisclosure.FULL and record.prompt is not None:
        prompt["text"] = record.prompt

    model: dict[str, str] = {"level": settings.model_disclosure.value}
    if settings.model_disclosure is ModelDisclosure.FAMILY and record.model_family:
        model["family"] = record.model_family
    elif settings.model_disclosure is ModelDisclosure.MODEL_ID and record.model_id:
        model["id"] = record.model_id
    elif settings.model_disclosure is ModelDisclosure.MODEL_ID_AND_VERSION:
        if record.model_id:
            model["id"] = record.model_id
        if record.model_version:
            model["version"] = record.model_version
        if record.model_hash:
            model["sha256"] = record.model_hash

    workflow: dict[str, Any] = {"level": settings.workflow_disclosure.value}
    if settings.workflow_disclosure is WorkflowDisclosure.ID and record.workflow_id:
        workflow["id"] = record.workflow_id
    elif (
        settings.workflow_disclosure is WorkflowDisclosure.HASH and record.workflow_json is not None
    ):
        workflow["sha256"] = hashlib.sha256(_canonical_json(record.workflow_json)).hexdigest()
    elif (
        settings.workflow_disclosure is WorkflowDisclosure.FULL and record.workflow_json is not None
    ):
        workflow["data"] = record.workflow_json

    return {
        "schema": "comfyui-support-tools/transparency-sidecar",
        "schema_version": 1,
        "eu_transparency_assist_enabled": True,
        "generated_or_modified": record.classification.value,
        "content_type": record.content_type,
        "application": {"name": record.application, "version": record.application_version},
        "backend": record.backend,
        "generation_time": record.generated_at,
        "output": {"sha256": output_sha256},
        "source_assets": [{"sha256": sha256_file(path)} for path in record.source_assets],
        "edit_actions": [asdict(action) for action in record.actions],
        "disclosure": {"prompt": prompt, "model": model, "workflow": workflow},
        "deepfake_disclosure_assist": {
            "enabled": settings.deepfake_disclosure_assist,
            "user_indicated_applicable": record.deepfake_disclosure_applicable,
            "represents_real_person_place_or_event": record.represents_real_person_place_or_event,
            "visible_disclosure": settings.visible_disclosure,
            "visible_label": settings.visible_disclosure_label
            if settings.visible_disclosure
            else None,
        },
        "c2pa_manifest_status": c2pa_manifest_status,
        "user_overrides": list(record.user_overrides),
        "legal_profile": {
            "id": profile.id,
            "version": profile.profile_version,
            "jurisdiction": profile.jurisdiction,
            "regulation_reference": profile.regulation_reference,
            "effective_from": profile.effective_from,
            "references": list(profile.references),
        },
        "notice": "Technical provenance assistance only; this record does not determine legal obligations or guarantee compliance.",
    }


# {
# 責務: [ serialize_transparency_sidecar: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [payload]
# 戻り値: [処理結果]
# }
def serialize_transparency_sidecar(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )
