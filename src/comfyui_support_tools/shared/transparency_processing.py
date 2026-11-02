"""Apply opt-in provenance to generated image outputs without changing originals."""

import json
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from comfyui_support_tools.shared.c2pa_adapter import C2paAdapter, SignerProvider
from comfyui_support_tools.shared.output_artifact import ConflictPolicy, atomic_write_bytes
from comfyui_support_tools.shared.png_transparency_metadata import (
    create_png_transparency_copy,
    verify_png_transparency,
)
from comfyui_support_tools.shared.transparency_contracts import (
    MediaClassification,
    ModelDisclosure,
    PromptDisclosure,
    ProvenanceAction,
    ProvenanceRecord,
    TransparencySettings,
    VerificationFailurePolicy,
    WorkflowDisclosure,
    resolve_transparency_enabled,
)
from comfyui_support_tools.shared.transparency_preferences import TransparencyPreferenceStore
from comfyui_support_tools.shared.transparency_sidecar import (
    build_transparency_sidecar,
    serialize_transparency_sidecar,
    sha256_bytes,
    sha256_file,
)

MAX_WORKFLOW_BYTES = 8 * 1024 * 1024


# {
# 責務: [ apply_generation_transparency: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [source_path, application_id, backend, prompt, model_id, model_family, model_version, workflow, transparency_options, preferences, signer_provider]
# 戻り値: [処理結果]
# }
def apply_generation_transparency(
    source_path: str | Path,
    *,
    application_id: str,
    backend: str,
    prompt: str,
    model_id: str | None = None,
    model_family: str | None = None,
    model_version: str | None = None,
    workflow: Mapping[str, Any] | None = None,
    transparency_options: Mapping[str, Any] | None = None,
    preferences: TransparencyPreferenceStore | None = None,
    signer_provider: SignerProvider | None = None,
) -> dict[str, Any]:
    """Add sidecar/PNG/C2PA copies when explicitly enabled; leave source untouched."""
    options = transparency_options or {}
    if not isinstance(options, Mapping):
        raise ValueError("transparency options must be an object")
    store = preferences or TransparencyPreferenceStore()
    try:
        global_enabled = store.global_enabled()
        application_override = store.application_override(application_id)
    except (OSError, ValueError):
        # Corrupt/stale preferences cannot enable disclosure or alter defaults.
        global_enabled, application_override = False, None
    requested = options.get("enabled")
    if requested is not None and not isinstance(requested, bool):
        raise ValueError("transparency enabled option must be boolean")
    enabled = resolve_transparency_enabled(global_enabled, application_override, requested)
    if not enabled:
        return {"image": str(source_path), "transparency_enabled": False, "artifacts": []}

    source = Path(source_path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("generated asset must be a regular file")
    configuration = _resolve_transparency_configuration(
        options, workflow, model_id, model_family, model_version, signer_provider
    )
    settings, record, sign_c2pa, write_png, write_sidecar, label = _build_transparency_record(
        configuration, options, backend, prompt, model_id, model_family, model_version
    )
    output_path = source
    output_bytes = None
    c2pa_status: dict[str, Any] | str = "not_requested"

    if sign_c2pa:
        signed_path = source.with_name(f"{source.stem}.transparency.c2pa{source.suffix}")
        with tempfile.TemporaryDirectory(
            prefix="transparency-stage-", dir=source.parent
        ) as staging:
            staged = Path(staging) / f"signed{source.suffix}"
            report = C2paAdapter().sign(source, staged, record, signer_provider, settings)
            output_bytes = staged.read_bytes()
            c2pa_status = report.to_dict()
        output_path = signed_path
    elif write_png:
        embed_payload = build_transparency_sidecar(
            record, settings, output_sha256="", c2pa_manifest_status=c2pa_status
        )
        embed_payload.pop("output")
        output_bytes = create_png_transparency_copy(
            source,
            embed_payload,
            visible_disclosure_label=label,
        )
        if not verify_png_transparency(output_bytes, embed_payload):
            raise ValueError("PNG provenance metadata did not survive export verification")
        output_path = source.with_name(f"{source.stem}.transparency.png")

    if output_bytes is not None:
        atomic_write_bytes(output_path, output_bytes, policy=ConflictPolicy.FAIL)
    output_digest = sha256_bytes(output_bytes) if output_bytes is not None else sha256_file(source)
    sidecar_path = source.with_suffix(source.suffix + ".transparency.json")
    artifacts = [str(output_path)] if output_path != source else []
    if write_sidecar:
        payload = build_transparency_sidecar(
            record,
            settings,
            output_sha256=output_digest,
            c2pa_manifest_status=c2pa_status,
        )
        atomic_write_bytes(
            sidecar_path,
            serialize_transparency_sidecar(payload),
            policy=ConflictPolicy.FAIL,
            validator=lambda staged: json.loads(staged.read_text(encoding="utf-8")),
        )
        artifacts.append(str(sidecar_path))
    return {
        "image": str(output_path),
        "source_image": str(source),
        "transparency_enabled": True,
        "transparency_sidecar": str(sidecar_path) if write_sidecar else None,
        "c2pa_manifest_status": c2pa_status,
        "artifacts": artifacts,
    }


# {
# 責務: [ _resolve_transparency_configuration: 開示と出力設定を検証する ]
# 処理: [ 1: 開示レベルを検証, 2: workflowと出力形式の制約を検証 ]
# 引数: [options, workflow, model_id, model_family, model_version, signer_provider]
# 戻り値: [検証済み設定値]
# }
def _resolve_transparency_configuration(
    options, workflow, model_id, model_family, model_version, signer_provider
):
    prompt_level = PromptDisclosure(options.get("prompt_disclosure", "none"))
    model_level = ModelDisclosure(options.get("model_disclosure", "none"))
    workflow_level = WorkflowDisclosure(options.get("workflow_disclosure", "none"))
    summary = options.get("sanitized_prompt_summary")
    if prompt_level is PromptDisclosure.SANITIZED_SUMMARY and not summary:
        raise ValueError("sanitized prompt disclosure requires a user-provided summary")
    if summary is not None and not isinstance(summary, str):
        raise ValueError("sanitized prompt summary must be text")
    if model_level is ModelDisclosure.FAMILY and not model_family:
        raise ValueError("model family disclosure requires a model family")
    if (
        model_level in {ModelDisclosure.MODEL_ID, ModelDisclosure.MODEL_ID_AND_VERSION}
        and not model_id
    ):
        raise ValueError("model identifier disclosure requires a model id")
    model_hash = options.get("model_hash")
    if model_level is ModelDisclosure.MODEL_ID_AND_VERSION and not model_version and not model_hash:
        raise ValueError("model id plus version/hash disclosure requires a version or hash")
    if model_hash is not None and not isinstance(model_hash, str):
        raise ValueError("model hash must be text")
    workflow_id = options.get("workflow_id")
    if workflow_level is WorkflowDisclosure.ID and not workflow_id:
        raise ValueError("workflow id disclosure requires a workflow id")
    workflow_data = (
        dict(workflow)
        if workflow is not None
        and workflow_level in {WorkflowDisclosure.HASH, WorkflowDisclosure.FULL}
        else None
    )
    if (
        workflow_data is not None
        and len(json.dumps(workflow_data, ensure_ascii=False).encode("utf-8")) > MAX_WORKFLOW_BYTES
    ):
        raise ValueError("workflow metadata exceeds 8 MiB")
    if (
        workflow_level in {WorkflowDisclosure.HASH, WorkflowDisclosure.FULL}
        and workflow_data is None
    ):
        label = "full" if workflow_level is WorkflowDisclosure.FULL else "hash"
        raise ValueError(f"{label} workflow disclosure requires an API-format workflow")
    sign_c2pa = options.get("sign_c2pa", False)
    write_png = options.get("write_png_metadata", False)
    write_sidecar = options.get("write_sidecar", True)
    if any(not isinstance(value, bool) for value in (sign_c2pa, write_png, write_sidecar)):
        raise ValueError("transparency output options must be boolean")
    if not (sign_c2pa or write_png or write_sidecar):
        raise ValueError("at least one transparency output format must be selected")
    if sign_c2pa and write_png:
        raise ValueError("C2PA and PNG text metadata require separate output workflows")
    visible = options.get("visible_disclosure", False)
    if not isinstance(visible, bool):
        raise ValueError("visible disclosure option must be boolean")
    if visible and not write_png:
        raise ValueError("visible disclosure requires a separate PNG copy")
    deepfake = options.get("deepfake_disclosure_assist", False)
    applicable = options.get("deepfake_disclosure_applicable", False)
    real_person = options.get("represents_real_person_place_or_event", False)
    if any(not isinstance(value, bool) for value in (deepfake, applicable, real_person)):
        raise ValueError("deepfake disclosure options must be boolean")
    if sign_c2pa and signer_provider is None:
        raise ValueError("C2PA signing requires an injected secure signer provider")
    return locals()


# {
# 責務: [ _build_transparency_record: 検証済み設定からprovenance recordを組み立てる ]
# 処理: [ 1: TransparencySettingsを作成, 2: ProvenanceRecordを作成 ]
# 引数: [configuration, options, backend, prompt, model_id, model_family, model_version]
# 戻り値: [設定、record、出力方式]
# }
def _build_transparency_record(
    configuration, options, backend, prompt, model_id, model_family, model_version
):
    prompt_level = configuration["prompt_level"]
    model_level = configuration["model_level"]
    workflow_level = configuration["workflow_level"]
    sign_c2pa = configuration["sign_c2pa"]
    write_png = configuration["write_png"]
    write_sidecar = configuration["write_sidecar"]
    visible = configuration["visible"]
    label = "AI-generated" if visible else None
    settings = TransparencySettings(
        enabled=True,
        prompt_disclosure=prompt_level,
        model_disclosure=model_level,
        workflow_disclosure=workflow_level,
        write_sidecar=write_sidecar,
        write_png_metadata=write_png,
        sign_c2pa=sign_c2pa,
        visible_disclosure=visible,
        visible_disclosure_label=label,
        verification_failure_policy=VerificationFailurePolicy(
            options.get("verification_failure_policy", "error")
        ),
        deepfake_disclosure_assist=configuration["deepfake"],
    )
    record = ProvenanceRecord(
        classification=MediaClassification.GENERATED,
        content_type="image",
        application="comfyUI_support_tools",
        application_version="unknown",
        backend=backend,
        prompt=prompt,
        sanitized_prompt_summary=options.get("sanitized_prompt_summary"),
        model_family=model_family,
        model_id=model_id,
        model_version=model_version,
        model_hash=options.get("model_hash"),
        workflow_id=options.get("workflow_id"),
        workflow_json=configuration["workflow_data"],
        deepfake_disclosure_applicable=configuration["applicable"],
        represents_real_person_place_or_event=configuration["real_person"],
        actions=(
            ProvenanceAction(
                operation="txt2img", ai_involvement=True, user_oversight="prompt_guided"
            ),
        ),
    )
    return settings, record, sign_c2pa, write_png, write_sidecar, label
