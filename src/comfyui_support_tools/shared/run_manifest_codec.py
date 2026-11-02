"""Schema migration, serialization, and validation for run manifests."""

import hashlib
import json
import math
import os
from collections.abc import Mapping
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from comfyui_support_tools.shared.contracts.run_manifest import (
    RUN_MANIFEST_SCHEMA_VERSION,
    ArtifactReference,
    ComponentVersion,
    PrivacyMode,
    ReproducibilityLevel,
    RunDecision,
    RunLineage,
    RunManifest,
    RunManifestEvent,
    RunStatus,
)

MAX_RUN_MANIFEST_BYTES = 16 * 1024 * 1024


# {
#   責務: [_artifact_stat_identity: artifact path/descriptorのsnapshot identityを作る]
#   処理: [1: device/inode/type/size/mtime/ctimeを取得する]
#   引数: [metadata: stat result]
#   戻り値: [identity: immutable stat tuple]
# }
def _artifact_stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


# {
#   責務: [_validate_manifest_event: JSONL event identity/time/payloadを保存前に検証する]
#   処理: [1: run ID/sequence/time/typeを確認する 2: payload JSONとtupleを検証する]
#   引数: [event: manifest lifecycle event]
#   戻り値: []
# }
def _validate_manifest_event(event: RunManifestEvent) -> None:
    if (
        not isinstance(event, RunManifestEvent)
        or not isinstance(event.run_id, str)
        or type(event.sequence) is not int
        or event.sequence < 0
        or not isinstance(event.event_type, str)
        or not event.event_type.strip()
        or not isinstance(event.payload, tuple)
        or isinstance(event.created_at, bool)
        or not isinstance(event.created_at, (int, float))
        or not math.isfinite(event.created_at)
        or event.created_at < 0
    ):
        raise ValueError("run manifest event is invalid")
    _safe_run_id(event.run_id)
    if not all(
        isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
        for item in event.payload
    ):
        raise ValueError("run manifest event payload is invalid")
    _canonical_json(asdict(event))


# {
#   責務: [run_manifest_to_dict: manifest contractをversioned JSON-safe mappingへ変換する]
#   処理: [1: nested dataclassを展開する 2: Enumをstable stringへ変換する]
#   引数: [manifest: run record]
#   戻り値: [payload: schema versioned object]
# }
def run_manifest_to_dict(manifest: RunManifest) -> dict:
    return _json_safe(manifest)


# {
#   責務: [_load_manifest_file: integrity envelopeを検証してmigration済manifestを復元する]
#   処理: [1: JSON parse 2: optional digest check 3: migration 4: contract rehydrate]
#   引数: [path: manifest path]
#   戻り値: [manifest: validated record]
# }
def _load_manifest_file(path: Path) -> RunManifest:
    try:
        manifest_path = Path(path)
        if manifest_path.stat().st_size > MAX_RUN_MANIFEST_BYTES:
            raise ValueError("run manifest exceeds maximum size")
        encoded = manifest_path.read_bytes()
        if len(encoded) > MAX_RUN_MANIFEST_BYTES:
            raise ValueError("run manifest exceeds maximum size")
        envelope = json.loads(encoded)
    except (OSError, UnicodeError, ValueError) as error:
        raise ValueError("run manifest cannot be read") from error
    if isinstance(envelope, dict) and "manifest" in envelope:
        payload = envelope["manifest"]
        expected_digest = envelope.get("manifest_sha256")
        if expected_digest != hashlib.sha256(_canonical_json(payload)).hexdigest():
            raise ValueError("run manifest digest does not match")
    else:
        payload = envelope
    payload = migrate_run_manifest_payload(payload)
    return _manifest_from_dict(payload)


# {
#   責務: [migrate_run_manifest_payload: prior schema payloadをcurrent schemaへ段階migrationする]
#   処理: [1: source schema versionを確認する 2: supported additive migrationsを適用する]
#   引数: [payload: parsed manifest mapping]
#   戻り値: [migrated: schema version 1 mapping]
# }
def migrate_run_manifest_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("run manifest payload must be an object")
    current = dict(payload)
    version = current.get("schema_version", 0)
    if type(version) is not int or version < 0:
        raise ValueError("run manifest schema version is invalid")
    if version == 0:
        current.setdefault("random_selections", [])
        current.setdefault("component_versions", [])
        current.setdefault("environment", [])
        current.setdefault("selected_candidate_refs", [])
        current.setdefault("rejected_candidate_refs", [])
        current.setdefault("repair_history", [])
        current.setdefault("user_overrides", [])
        current.setdefault("lineage", {})
        current.setdefault("provenance", [])
        current.setdefault("privacy_modes", [])
        current.setdefault("reproducibility", ReproducibilityLevel.BEST_EFFORT.value)
        current["schema_version"] = 1
        version = 1
    if version == 1:
        current.setdefault("job_id", "")
        current["schema_version"] = 2
        version = 2
    if version != RUN_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported run manifest schema version: {version}")
    return current


# {
#   責務: [_manifest_from_dict: JSON mappingをnested immutable run contractsへ復元する]
#   処理: [1: enum/nested referencesを復元する 2: manifest invariantを検証する]
#   引数: [payload: schema version mapping]
#   戻り値: [manifest: validated RunManifest]
# }
def _manifest_from_dict(payload: dict) -> RunManifest:
    try:
        manifest = RunManifest(
            run_id=payload["run_id"],
            application_id=payload["application_id"],
            application_version=payload["application_version"],
            settings_schema_version=payload["settings_schema_version"],
            started_at=payload["started_at"],
            finished_at=payload.get("finished_at"),
            status=RunStatus(payload["status"]),
            reproducibility=ReproducibilityLevel(payload["reproducibility"]),
            input_refs=tuple(_artifact_from_dict(item) for item in payload.get("input_refs", ())),
            resolved_settings=tuple(tuple(item) for item in payload.get("resolved_settings", ())),
            random_seeds=tuple((str(key), value) for key, value in payload.get("random_seeds", ())),
            random_selections=tuple(tuple(item) for item in payload.get("random_selections", ())),
            component_versions=tuple(
                ComponentVersion(**item) for item in payload.get("component_versions", ())
            ),
            environment=tuple(tuple(item) for item in payload.get("environment", ())),
            output_artifacts=tuple(
                _artifact_from_dict(item) for item in payload.get("output_artifacts", ())
            ),
            warnings=tuple(payload.get("warnings", ())),
            errors=tuple(payload.get("errors", ())),
            decisions=tuple(_decision_from_dict(item) for item in payload.get("decisions", ())),
            selected_candidate_refs=tuple(payload.get("selected_candidate_refs", ())),
            rejected_candidate_refs=tuple(payload.get("rejected_candidate_refs", ())),
            repair_history=tuple(
                _decision_from_dict(item) for item in payload.get("repair_history", ())
            ),
            user_overrides=tuple(tuple(item) for item in payload.get("user_overrides", ())),
            lineage=RunLineage(
                **{
                    **payload.get("lineage", {}),
                    "child_run_ids": tuple(payload.get("lineage", {}).get("child_run_ids", ())),
                }
            ),
            provenance=tuple(tuple(item) for item in payload.get("provenance", ())),
            privacy_modes=tuple(
                (key, PrivacyMode(value)) for key, value in payload.get("privacy_modes", ())
            ),
            job_id=payload.get("job_id", ""),
            schema_version=payload["schema_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("run manifest schema payload is invalid") from error
    try:
        _validate_manifest(manifest)
    except (TypeError, AttributeError) as error:
        raise ValueError("run manifest schema payload is invalid") from error
    return manifest


# {
#   責務: [_artifact_from_dict: artifact mappingのtiming metadataをimmutable tuple化する]
#   処理: [1: dataclass mappingをcopyする 2: nested timing pairsをtupleへ変換する]
#   引数: [payload: artifact object mapping]
#   戻り値: [artifact: immutable reference]
# }
def _artifact_from_dict(payload) -> ArtifactReference:
    return ArtifactReference(
        **{
            **payload,
            "media_timing": tuple(tuple(item) for item in payload.get("media_timing", ())),
        }
    )


# {
#   責務: [_decision_from_dict: decision mappingをimmutable detail tupleへ復元する]
#   処理: [1: payload fieldsをcopyする 2: detailsをtuple化する]
#   引数: [payload: decision mapping]
#   戻り値: [decision: immutable RunDecision]
# }
def _decision_from_dict(payload) -> RunDecision:
    return RunDecision(
        **{**payload, "details": tuple(tuple(item) for item in payload.get("details", ()))}
    )


# {
#   責務: [_validate_manifest: schema, identity, time, and random seed invariantsを検証する]
#   処理: [1: required ID/time/statusを確認する 2: JSON-safe valuesとseedsを検証する]
#   引数: [manifest: run contract]
#   戻り値: []
# }
def _validate_manifest(manifest: RunManifest) -> None:
    if not isinstance(manifest, RunManifest):
        raise ValueError("manifest must be a RunManifest")
    if (
        type(manifest.schema_version) is not int
        or manifest.schema_version != RUN_MANIFEST_SCHEMA_VERSION
    ):
        raise ValueError("unsupported run manifest schema version")
    if (
        not isinstance(manifest.run_id, str)
        or not manifest.run_id
        or len(manifest.run_id) > 120
        or not isinstance(manifest.application_id, str)
        or not manifest.application_id.strip()
        or not isinstance(manifest.application_version, str)
        or not isinstance(manifest.settings_schema_version, str)
        or not manifest.settings_schema_version.strip()
        or not isinstance(manifest.job_id, str)
        or not isinstance(manifest.status, RunStatus)
        or not isinstance(manifest.reproducibility, ReproducibilityLevel)
        or not isinstance(manifest.lineage, RunLineage)
    ):
        raise ValueError("run ID, application ID, and settings schema version are required")
    _safe_run_id(manifest.run_id)
    timestamps = (manifest.started_at,) + (
        () if manifest.finished_at is None else (manifest.finished_at,)
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in timestamps
    ) or (manifest.finished_at is not None and manifest.finished_at < manifest.started_at):
        raise ValueError("run timestamps are invalid")
    if manifest.status is RunStatus.RUNNING and manifest.finished_at is not None:
        raise ValueError("running manifest cannot have a finish time")
    if manifest.status is not RunStatus.RUNNING and manifest.finished_at is None:
        raise ValueError("terminal manifest requires a finish time")
    _validate_manifest_collection_types(manifest)
    _validate_manifest_record_values(manifest)


# {
#   責務: [_validate_manifest_collection_types: immutable record collectionとkey/value shapeを検証する]
#   処理: [1: tuple contractを確認する 2: artifact/decision/pair/refの構造を確認する]
#   引数: [manifest: run contract]
#   戻り値: []
# }
def _validate_manifest_collection_types(manifest: RunManifest) -> None:
    tuple_fields = (
        manifest.input_refs,
        manifest.resolved_settings,
        manifest.random_seeds,
        manifest.random_selections,
        manifest.component_versions,
        manifest.environment,
        manifest.output_artifacts,
        manifest.warnings,
        manifest.errors,
        manifest.decisions,
        manifest.selected_candidate_refs,
        manifest.rejected_candidate_refs,
        manifest.repair_history,
        manifest.user_overrides,
        manifest.provenance,
        manifest.privacy_modes,
        manifest.lineage.child_run_ids,
    )
    if not all(isinstance(value, tuple) for value in tuple_fields):
        raise ValueError("manifest collections must be immutable tuples")
    if not all(
        isinstance(item, ArtifactReference)
        for item in (*manifest.input_refs, *manifest.output_artifacts)
    ):
        raise ValueError("manifest artifact references are invalid")
    if not all(isinstance(item, ComponentVersion) for item in manifest.component_versions):
        raise ValueError("manifest component versions are invalid")
    if not all(
        isinstance(item.component_id, str)
        and isinstance(item.version, str)
        and isinstance(item.reference, str)
        for item in manifest.component_versions
    ):
        raise ValueError("manifest component version fields are invalid")
    if not all(
        isinstance(item, RunDecision) for item in (*manifest.decisions, *manifest.repair_history)
    ):
        raise ValueError("manifest decisions are invalid")
    if not all(isinstance(item, str) for item in (*manifest.warnings, *manifest.errors)):
        raise ValueError("manifest warnings and errors must be strings")
    pair_fields = (
        manifest.resolved_settings,
        manifest.random_seeds,
        manifest.random_selections,
        manifest.environment,
        manifest.user_overrides,
        manifest.provenance,
    )
    if any(
        not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str)
        for pairs in pair_fields
        for pair in pairs
    ):
        raise ValueError("manifest mapping fields must contain string-key/value pairs")
    if not all(
        isinstance(item, str)
        for item in (*manifest.selected_candidate_refs, *manifest.rejected_candidate_refs)
    ):
        raise ValueError("candidate references must be strings")


# {
#   責務: [_validate_manifest_record_values: seeds/privacy/artifact/decision valuesを検証してJSON-safeを保証する]
#   処理: [1: seed/privacy invariantを検証する 2: metadata valuesを検証しcanonicalizeする]
#   引数: [manifest: run contract]
#   戻り値: []
# }
def _validate_manifest_record_values(manifest: RunManifest) -> None:
    seed_names = [name for name, _seed in manifest.random_seeds]
    if any(not isinstance(name, str) or not name for name in seed_names) or len(
        set(seed_names)
    ) != len(seed_names):
        raise ValueError("random seed names must be nonempty and unique")
    privacy_keys = [key for key, _mode in manifest.privacy_modes]
    if (
        any(not isinstance(key, str) or not key for key in privacy_keys)
        or len(set(privacy_keys)) != len(privacy_keys)
        or not all(isinstance(mode, PrivacyMode) for _key, mode in manifest.privacy_modes)
    ):
        raise ValueError("manifest privacy modes are invalid")
    modes = dict(manifest.privacy_modes)
    seed_mode = modes.get("random_seeds", PrivacyMode.FULL)
    for key, seed in manifest.random_seeds:
        mode = modes.get(f"random_seeds.{key}", seed_mode)
        if mode is PrivacyMode.FULL:
            _validate_seed(seed)
        elif not isinstance(seed, Mapping):
            raise ValueError("redacted random seeds must use a privacy-safe object")
    for artifact in (*manifest.input_refs, *manifest.output_artifacts):
        if (
            not isinstance(artifact.artifact_id, str)
            or not isinstance(artifact.uri, str)
            or (
                artifact.size_bytes is not None
                and (type(artifact.size_bytes) is not int or artifact.size_bytes < 0)
            )
            or not isinstance(artifact.sha256, str)
            or not isinstance(artifact.media_type, str)
            or not isinstance(artifact.media_timing, tuple)
            or any(
                not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str)
                for pair in artifact.media_timing
            )
        ):
            raise ValueError("manifest artifact metadata is invalid")
    for decision in (*manifest.decisions, *manifest.repair_history):
        if (
            not all(
                isinstance(value, str)
                for value in (
                    decision.decision_id,
                    decision.category,
                    decision.outcome,
                    decision.reason,
                    decision.candidate_ref,
                )
            )
            or not isinstance(decision.details, tuple)
            or any(
                not isinstance(pair, tuple) or len(pair) != 2 or not isinstance(pair[0], str)
                for pair in decision.details
            )
        ):
            raise ValueError("manifest decision fields are invalid")
        if decision.score is not None and (
            isinstance(decision.score, bool)
            or not isinstance(decision.score, (int, float))
            or not math.isfinite(decision.score)
        ):
            raise ValueError("manifest decision score is invalid")
    _canonical_json(run_manifest_to_dict(manifest))


# {
#   責務: [_validate_seed: random seedをJSON integer range内で確認する]
#   処理: [1: bool/int distinctionを確認する 2: signed 256-bit rangeを検証する]
#   引数: [value: seed value]
#   戻り値: [seed: validated integer]
# }
def _validate_seed(value: int) -> int:
    if type(value) is not int or not 0 <= value < 2**256:
        raise ValueError("random seeds must be integers in 0..2^256-1")
    return value


# {
#   責務: [_safe_run_id: path injectionを拒否してrun ID file stemを返す]
#   処理: [1: allow-listed ASCII ID charsを検証する 2: safe filenameを返す]
#   引数: [run_id: stable ID]
#   戻り値: [safe: path-safe run ID]
# }
def _safe_run_id(run_id: str) -> str:
    if (
        not isinstance(run_id, str)
        or not run_id
        or len(run_id) > 120
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
            for character in run_id
        )
    ):
        raise ValueError("run ID contains unsafe filename characters")
    return run_id


# {
#   責務: [_json_safe: dataclass/enums/tuplesをJSON-compatible recursive valueへ変換する]
#   処理: [1: dataclassを展開する 2: Enum/Mapping/sequence/scalarを再帰変換する]
#   引数: [value: typed payload]
#   戻り値: [json value]
# }
def _json_safe(value):
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"value of type {type(value).__name__} is not JSON-compatible")


# {
#   責務: [_canonical_json: JSON objectをdeterministic UTF-8 bytesへencodeする]
#   処理: [1: key order/separatorsを固定する 2: NaN/Infinityを拒否する]
#   引数: [value: JSON-safe payload]
#   戻り値: [encoded: canonical bytes]
# }
def _canonical_json(value) -> bytes:
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
