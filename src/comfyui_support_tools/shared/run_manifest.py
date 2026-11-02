"""Versioned run provenance, privacy filtering, replay, and durable stores."""

import hashlib
import json
import os
import secrets
import stat
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Protocol

from comfyui_support_tools.shared.contracts.job_contracts import JobSnapshot
from comfyui_support_tools.shared.contracts.run_manifest import (
    RUN_MANIFEST_SCHEMA_VERSION,
    ArtifactReference,
    ComponentVersion,
    ManifestDifference,
    PrivacyMode,
    ReproducibilityLevel,
    RunDecision,
    RunLineage,
    RunManifest,
    RunManifestEvent,
    RunReplayRequest,
    RunStatus,
)
from comfyui_support_tools.shared.output_artifact import ConflictPolicy, atomic_write_bytes
from comfyui_support_tools.shared.run_manifest_codec import (
    MAX_RUN_MANIFEST_BYTES,
    _artifact_stat_identity,
    _canonical_json,
    _json_safe,
    _load_manifest_file,
    _safe_run_id,
    _validate_manifest,
    _validate_manifest_event,
    _validate_seed,
    run_manifest_to_dict,
)
from comfyui_support_tools.shared.run_manifest_codec import (
    migrate_run_manifest_payload as migrate_run_manifest_payload,
)
from comfyui_support_tools.shared.run_manifest_privacy import (
    _secure_artifact,
    _secure_decision,
    _secure_locator,
    _secure_mapping,
    _secure_strings,
)

MAX_RUN_EVENT_BYTES = 1024 * 1024
MAX_RUN_EVENT_STREAM_BYTES = 64 * 1024 * 1024


# {
#   責務: [RunManifestStore: storage adapterのsave/load protocolを定義する]
#   フィールド: [versioned RunManifest read/write operations]
# }
class RunManifestStore(Protocol):
    # {
    #   責務: [save: immutable manifestをdurable storageへ保存する]
    #   処理: [1: schema/integrityを検証する 2: manifest refを返す]
    #   引数: [manifest: run record]
    #   戻り値: [reference: durable run reference]
    # }
    def save(self, manifest: RunManifest) -> str: ...

    # {
    #   責務: [load: run IDからversion migrate済みmanifestを読む]
    #   処理: [1: storage adapterからJSONを読む 2: schemaをvalidateする]
    #   引数: [run_id: stable run id]
    #   戻り値: [manifest: restored run record]
    # }
    def load(self, run_id: str) -> RunManifest: ...


# {
#   責務: [JsonRunManifestStore: atomic JSON documentでrun manifestを永続化する]
#   フィールド: [manifest root directory、process-local lock]
# }
class JsonRunManifestStore:
    # {
    #   責務: [__init__: manifest JSON storeを初期化する]
    #   処理: [1: root pathを保存する 2: store lockを作る]
    #   引数: [root: manifest directory]
    #   戻り値: []
    # }
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.Lock()

    # {
    #   責務: [save: manifest digest envelopeをatomic JSON fileへ保存する]
    #   処理: [1: schemaを確認する 2: canonical digestを付ける 3: atomic writerへ渡す]
    #   引数: [manifest: validated run record]
    #   戻り値: [reference: JSON path]
    # }
    def save(self, manifest: RunManifest) -> str:
        _validate_manifest(manifest)
        payload = run_manifest_to_dict(manifest)
        envelope = {
            "manifest": payload,
            "manifest_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
        }
        encoded = _canonical_json(envelope) + b"\n"
        if len(encoded) > MAX_RUN_MANIFEST_BYTES:
            raise ValueError("run manifest exceeds maximum size")
        target = self.root / f"{_safe_run_id(manifest.run_id)}.json"
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_bytes(
                target,
                encoded,
                policy=ConflictPolicy.OVERWRITE,
                validator=lambda staged: _load_manifest_file(staged),
            )
        return str(target)

    # {
    #   責務: [load: JSON manifest envelopeをintegrity/schema検証して復元する]
    #   処理: [1: JSON fileを読む 2: digestを検証する 3: schema migration後にcontractを復元する]
    #   引数: [run_id: stable run id]
    #   戻り値: [manifest: restored run record]
    # }
    def load(self, run_id: str) -> RunManifest:
        path = self.root / f"{_safe_run_id(run_id)}.json"
        return _load_manifest_file(path)


# {
#   責務: [JsonLineRunEventStore: lifecycle/progress eventsをbounded JSONL recordsとして保存する]
#   フィールド: [event directory、append lock]
# }
class JsonLineRunEventStore:
    # {
    #   責務: [__init__: JSONL event storeを初期化する]
    #   処理: [1: events directoryを保存する 2: append lockを作る]
    #   引数: [root: JSONL directory]
    #   戻り値: []
    # }
    def __init__(self, root: Path):
        self.root = Path(root)
        self._lock = threading.Lock()

    # {
    #   責務: [append: 1行JSON eventをappend/fsyncする]
    #   処理: [1: eventをvalidateする 2: newline JSON bytesをappend 3: file dataをflushする]
    #   引数: [event: ordered run event]
    #   戻り値: [path: JSONL event stream]
    # }
    def append(self, event: RunManifestEvent) -> Path:
        _validate_manifest_event(event)
        path = self.root / f"{_safe_run_id(event.run_id)}.jsonl"
        data = _canonical_json(asdict(event)) + b"\n"
        if len(data) > MAX_RUN_EVENT_BYTES:
            raise ValueError("run manifest event exceeds maximum size")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock:
            current_size = path.stat().st_size if path.exists() else 0
            if current_size + len(data) > MAX_RUN_EVENT_STREAM_BYTES:
                raise ValueError("run manifest event stream exceeds maximum size")
            existing = self.load(event.run_id) if path.exists() else ()
            if existing and event.sequence <= existing[-1].sequence:
                raise ValueError("run event sequence must increase")
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                pending = memoryview(data)
                while pending:
                    written = os.write(descriptor, pending)
                    if written <= 0:
                        raise OSError("run event append made no progress")
                    pending = pending[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return path

    # {
    #   責務: [load: run event JSONLをsequence順に読み取る]
    #   処理: [1: lineごとにJSON parseする 2: malformed/duplicate sequenceを拒否する]
    #   引数: [run_id: stable run id]
    #   戻り値: [events: immutable sequence-sorted events]
    # }
    def load(self, run_id: str) -> tuple[RunManifestEvent, ...]:
        path = self.root / f"{_safe_run_id(run_id)}.jsonl"
        try:
            if path.stat().st_size > MAX_RUN_EVENT_STREAM_BYTES:
                raise ValueError("run manifest event stream exceeds maximum size")
            records = [
                json.loads(line)
                for line in path.read_bytes().decode("utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, UnicodeError, ValueError) as error:
            raise ValueError("run event stream cannot be read") from error
        try:
            events = tuple(
                RunManifestEvent(
                    run_id=record["run_id"],
                    sequence=record["sequence"],
                    created_at=record["created_at"],
                    event_type=record["event_type"],
                    payload=tuple(tuple(item) for item in record.get("payload", ())),
                )
                for record in records
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("run event stream contains invalid record") from error
        sequences = [event.sequence for event in events]
        if any(event.run_id != run_id for event in events) or len(set(sequences)) != len(sequences):
            raise ValueError("run event identity or sequence is invalid")
        for event in events:
            _validate_manifest_event(event)
        return tuple(sorted(events, key=lambda item: item.sequence))


# {
#   責務: [create_run_manifest: application execution contextからrunning manifestを作成する]
#   処理: [1: privacy policyを解決する 2: inputs/settings/metadataをfilterする 3: stable run identity/seedを割り当てる]
#   引数: [application_id/version/settings schema, inputs/settings, seeds/selections, components/environment, privacy, lineage, provenance]
#   戻り値: [manifest: immutable running record]
# }
def create_run_manifest(
    application_id: str,
    application_version: str,
    settings_schema_version: str,
    *,
    input_refs: Sequence[ArtifactReference] = (),
    resolved_settings: Mapping | None = None,
    random_seeds: Mapping[str, int] | None = None,
    random_selections: Mapping | None = None,
    component_versions: Sequence[ComponentVersion] = (),
    environment: Mapping | None = None,
    reproducibility: ReproducibilityLevel | str = ReproducibilityLevel.BEST_EFFORT,
    privacy_modes: Mapping[str, PrivacyMode | str] | None = None,
    user_overrides: Mapping | None = None,
    lineage: RunLineage | None = None,
    provenance: Mapping | None = None,
    run_id: str | None = None,
    job_id: str = "",
    started_at: float | None = None,
) -> RunManifest:
    if (
        not isinstance(application_id, str)
        or not application_id.strip()
        or not isinstance(application_version, str)
        or not isinstance(settings_schema_version, str)
        or not settings_schema_version.strip()
        or not isinstance(job_id, str)
    ):
        raise ValueError("application ID and settings schema version are required")
    if any(
        value is not None and not isinstance(value, Mapping)
        for value in (
            resolved_settings,
            random_seeds,
            random_selections,
            environment,
            privacy_modes,
            user_overrides,
            provenance,
        )
    ):
        raise ValueError("run manifest settings and policies must be mappings")
    if not isinstance(input_refs, Sequence) or isinstance(input_refs, (str, bytes)):
        raise ValueError("input_refs must be a sequence of artifact references")
    if not all(isinstance(item, ArtifactReference) for item in input_refs):
        raise ValueError("input_refs must contain ArtifactReference values")
    if not isinstance(component_versions, Sequence) or not all(
        isinstance(item, ComponentVersion) for item in component_versions
    ):
        raise ValueError("component_versions must contain ComponentVersion values")
    if lineage is not None and not isinstance(lineage, RunLineage):
        raise ValueError("lineage must be a RunLineage")
    if run_id is not None:
        if not isinstance(run_id, str):
            raise ValueError("run_id must be a string")
        _safe_run_id(run_id)
    if privacy_modes is not None and not all(isinstance(key, str) for key in privacy_modes):
        raise ValueError("privacy mode names must be strings")
    privacy = tuple(
        sorted((key, PrivacyMode(value)) for key, value in (privacy_modes or {}).items())
    )
    modes = dict(privacy)
    secure_inputs = tuple(_secure_artifact(item, modes) for item in input_refs)
    secure_settings = _secure_mapping("settings", resolved_settings or {}, modes)
    secure_environment = _secure_mapping("environment", environment or {}, modes)
    secure_overrides = _secure_mapping("user_overrides", user_overrides or {}, modes)
    secure_provenance = _secure_mapping("provenance", provenance or {}, modes)
    seed_values = {}
    for key, value in (random_seeds or {}).items():
        if not isinstance(key, str) or not key:
            raise ValueError("random seed names must be nonempty strings")
        seed_values[key] = _validate_seed(value)
    seeds = _secure_mapping("random_seeds", seed_values, modes)
    selections = _secure_mapping("random_selections", random_selections or {}, modes)
    if started_at is None:
        now = time.time()
    elif isinstance(started_at, bool) or not isinstance(started_at, (int, float)):
        raise ValueError("started_at must be a finite timestamp")
    else:
        now = float(started_at)
    manifest = RunManifest(
        run_id=run_id or f"run-{uuid.uuid4().hex}",
        application_id=application_id,
        application_version=application_version,
        settings_schema_version=settings_schema_version,
        started_at=now,
        finished_at=None,
        status=RunStatus.RUNNING,
        reproducibility=ReproducibilityLevel(reproducibility),
        input_refs=secure_inputs,
        resolved_settings=secure_settings,
        random_seeds=seeds,
        random_selections=selections,
        component_versions=tuple(component_versions),
        environment=secure_environment,
        output_artifacts=(),
        warnings=(),
        errors=(),
        decisions=(),
        selected_candidate_refs=(),
        rejected_candidate_refs=(),
        repair_history=(),
        user_overrides=secure_overrides,
        lineage=lineage or RunLineage(),
        provenance=secure_provenance,
        privacy_modes=privacy,
        job_id=job_id,
        schema_version=RUN_MANIFEST_SCHEMA_VERSION,
    )
    _validate_manifest(manifest)
    return manifest


# {
#   責務: [create_run_manifest_for_job: existing JobSnapshotへrun manifest contractをadaptする]
#   処理: [1: Job identityを確認する 2: caller metadataでmanifestを作りJob IDを結ぶ]
#   引数: [job: existing Job snapshot, application identity/version, manifest_options: settings/input/provenance fields]
#   戻り値: [manifest: Job-linked running RunManifest]
# }
def create_run_manifest_for_job(
    job: JobSnapshot,
    application_id: str,
    application_version: str,
    settings_schema_version: str,
    **manifest_options,
) -> RunManifest:
    if not isinstance(job, JobSnapshot) or not job.id:
        raise ValueError("a JobSnapshot with a stable ID is required")
    if "job_id" in manifest_options:
        raise ValueError("job_id is derived from the supplied JobSnapshot")
    return create_run_manifest(
        application_id,
        application_version,
        settings_schema_version,
        job_id=job.id,
        **manifest_options,
    )


# {
#   責務: [generate_random_seed: generated seedを明示生成してmanifestへ保存できる値を返す]
#   処理: [1: cryptographic system randomを使う 2: requested bit rangeへclampする]
#   引数: [bits: seed width]
#   戻り値: [seed: reproducible integer seed]
# }
def generate_random_seed(bits: int = 63) -> int:
    if type(bits) is not int or not 1 <= bits <= 256:
        raise ValueError("seed bits must be in 1..256")
    return secrets.randbits(bits)


# {
#   責務: [capture_artifact_reference: file pathをbounded content hash付きartifact refへ変換する]
#   処理: [1: file metadataを読む 2: requested時のみlimit内contentをSHA-256する]
#   引数: [path: filesystem artifact, artifact_id: stable ID, hash_content: content hash flag, hash_limit_bytes: maximum bytes]
#   戻り値: [reference: URI/size/optional hash]
# }
def capture_artifact_reference(
    path: Path,
    artifact_id: str = "",
    *,
    hash_content: bool = False,
    hash_limit_bytes: int = 8 * 1024 * 1024,
    media_type: str = "",
) -> ArtifactReference:
    if type(hash_limit_bytes) is not int or hash_limit_bytes < 0:
        raise ValueError("hash limit must be a nonnegative integer")
    if type(hash_content) is not bool:
        raise ValueError("hash_content must be a boolean")
    if not isinstance(artifact_id, str) or not isinstance(media_type, str):
        raise ValueError("artifact ID and media type must be strings")
    source = Path(path).expanduser().absolute()
    metadata = source.stat()
    digest = ""
    if hash_content and stat.S_ISREG(metadata.st_mode) and metadata.st_size <= hash_limit_bytes:
        hasher = hashlib.sha256()
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            if _artifact_stat_identity(os.fstat(descriptor)) != _artifact_stat_identity(metadata):
                raise OSError("artifact changed while its hash was captured")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
            if _artifact_stat_identity(os.fstat(descriptor)) != _artifact_stat_identity(metadata):
                raise OSError("artifact changed while its hash was captured")
            if _artifact_stat_identity(source.stat()) != _artifact_stat_identity(metadata):
                raise OSError("artifact path changed while its hash was captured")
        finally:
            os.close(descriptor)
        digest = hasher.hexdigest()
    return ArtifactReference(
        artifact_id or source.name,
        str(source),
        metadata.st_size if stat.S_ISREG(metadata.st_mode) else None,
        digest,
        (),
        media_type,
    )


# {
#   責務: [create_run_manifest_event: privacy-filtered lifecycle/progress eventを作る]
#   処理: [1: event payloadへprivacy modeを適用する 2: stable timestamp/sequenceを設定する]
#   引数: [run_id: parent run, sequence: monotonic number, event_type: event kind, payload: small event metadata, privacy_modes: field policy, created_at: optional time]
#   戻り値: [event: appendable JSONL record]
# }
def create_run_manifest_event(
    run_id: str,
    sequence: int,
    event_type: str,
    payload: Mapping | None = None,
    *,
    privacy_modes: Mapping[str, PrivacyMode | str] | None = None,
    created_at: float | None = None,
) -> RunManifestEvent:
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("event run ID is required")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("event type is required")
    if payload is not None and not isinstance(payload, Mapping):
        raise ValueError("event payload must be a mapping")
    if privacy_modes is not None and not isinstance(privacy_modes, Mapping):
        raise ValueError("privacy_modes must be a mapping")
    if created_at is None:
        timestamp = time.time()
    elif isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
        raise ValueError("event timestamp must be finite")
    else:
        timestamp = float(created_at)
    modes = {key: PrivacyMode(value) for key, value in (privacy_modes or {}).items()}
    event = RunManifestEvent(
        run_id,
        sequence,
        timestamp,
        event_type,
        _secure_mapping("event", payload or {}, modes),
    )
    _validate_manifest_event(event)
    return event


# {
#   責務: [finish_run_manifest: running manifestをterminal immutable recordに更新する]
#   処理: [1: current status/output/error/decision fieldsをmergeする 2: finished timeを設定する]
#   引数: [manifest: running record, status: terminal state, outputs/warnings/errors/decisions/repair history, finished_at]
#   戻り値: [finished: terminal run record]
# }
def finish_run_manifest(
    manifest: RunManifest,
    status: RunStatus | str,
    *,
    output_artifacts: Sequence[ArtifactReference] = (),
    warnings: Sequence[str] = (),
    errors: Sequence[str] = (),
    decisions: Sequence[RunDecision] = (),
    selected_candidate_refs: Sequence[str] = (),
    rejected_candidate_refs: Sequence[str] = (),
    repair_history: Sequence[RunDecision] = (),
    lineage: RunLineage | None = None,
    finished_at: float | None = None,
) -> RunManifest:
    _validate_manifest(manifest)
    terminal = RunStatus(status)
    if terminal is RunStatus.RUNNING:
        raise ValueError("finished manifest must have a terminal status")
    privacy = dict(manifest.privacy_modes)
    if not isinstance(output_artifacts, Sequence) or isinstance(output_artifacts, (str, bytes)):
        raise ValueError("output_artifacts must be a sequence of artifact references")
    if not all(isinstance(item, ArtifactReference) for item in output_artifacts):
        raise ValueError("output_artifacts must contain ArtifactReference values")
    if any(
        values is not None
        and (not isinstance(values, Sequence) or isinstance(values, (str, bytes)))
        for values in (
            warnings,
            errors,
            decisions,
            selected_candidate_refs,
            rejected_candidate_refs,
            repair_history,
        )
    ):
        raise ValueError("run outcome values must be sequences")
    candidate_mode = privacy.get("candidate_ref", PrivacyMode.FULL)
    if finished_at is None:
        finish_time = time.time()
    elif isinstance(finished_at, bool) or not isinstance(finished_at, (int, float)):
        raise ValueError("finished_at must be a finite timestamp")
    else:
        finish_time = float(finished_at)
    result = replace(
        manifest,
        status=terminal,
        finished_at=finish_time,
        output_artifacts=tuple(
            _secure_artifact(item, dict(manifest.privacy_modes)) for item in output_artifacts
        ),
        warnings=_secure_strings(warnings, privacy.get("warnings", PrivacyMode.FULL), 1000),
        errors=_secure_strings(errors, privacy.get("errors", PrivacyMode.FULL), 2000),
        decisions=tuple(_secure_decision(item, dict(manifest.privacy_modes)) for item in decisions),
        selected_candidate_refs=tuple(
            safe
            for item in selected_candidate_refs
            if (safe := _secure_locator(str(item)[:1024], candidate_mode))
        ),
        rejected_candidate_refs=tuple(
            safe
            for item in rejected_candidate_refs
            if (safe := _secure_locator(str(item)[:1024], candidate_mode))
        ),
        repair_history=tuple(
            _secure_decision(item, dict(manifest.privacy_modes)) for item in repair_history
        ),
        lineage=lineage or manifest.lineage,
    )
    _validate_manifest(result)
    return result


# {
#   責務: [manifest_replay_request: full settings privacyが許可されたrunからreplay requestを作る]
#   処理: [1: settingsがfullであることを確認する 2: same settings/seeds/input refsを返す]
#   引数: [manifest: source run manifest]
#   戻り値: [request: replayable application request]
# }
def manifest_replay_request(manifest: RunManifest) -> RunReplayRequest:
    modes = dict(manifest.privacy_modes)
    settings_mode = modes.get("settings", PrivacyMode.FULL)
    inputs_mode = modes.get("artifact_uri", PrivacyMode.FULL)
    seeds_mode = modes.get("random_seeds", PrivacyMode.FULL)
    selections_mode = modes.get("random_selections", PrivacyMode.FULL)
    if (
        settings_mode is not PrivacyMode.FULL
        or any(
            key.startswith("settings.") and mode is not PrivacyMode.FULL
            for key, mode in modes.items()
        )
        or any(
            modes.get(f"settings.{key}", settings_mode) is not PrivacyMode.FULL
            for key, _value in manifest.resolved_settings
        )
        or seeds_mode is not PrivacyMode.FULL
        or any(
            key.startswith("random_seeds.") and mode is not PrivacyMode.FULL
            for key, mode in modes.items()
        )
        or any(
            modes.get(f"random_seeds.{key}", seeds_mode) is not PrivacyMode.FULL
            for key, _value in manifest.random_seeds
        )
        or selections_mode is not PrivacyMode.FULL
        or any(
            key.startswith("random_selections.") and mode is not PrivacyMode.FULL
            for key, mode in modes.items()
        )
        or any(
            modes.get(f"random_selections.{key}", selections_mode) is not PrivacyMode.FULL
            for key, _value in manifest.random_selections
        )
    ):
        raise ValueError("manifest settings are redacted and cannot be replayed")
    if manifest.input_refs and (
        inputs_mode is not PrivacyMode.FULL or any(not item.uri for item in manifest.input_refs)
    ):
        raise ValueError("manifest input references are redacted and cannot be replayed")
    return RunReplayRequest(
        application_id=manifest.application_id,
        input_refs=manifest.input_refs,
        resolved_settings=manifest.resolved_settings,
        random_seeds=manifest.random_seeds,
        reproducibility=manifest.reproducibility,
        source_run_id=manifest.run_id,
    )


# {
#   責務: [compare_run_manifests: settings/seed/input/version/output outcome差分を返す]
#   処理: [1: selected fieldsをstable flattenする 2: differing field pathsを返す]
#   引数: [left/right: run manifests]
#   戻り値: [differences: sorted field-level comparison]
# }
def compare_run_manifests(left: RunManifest, right: RunManifest) -> tuple[ManifestDifference, ...]:
    fields = (
        "application_id",
        "application_version",
        "settings_schema_version",
        "reproducibility",
        "input_refs",
        "resolved_settings",
        "random_seeds",
        "random_selections",
        "component_versions",
        "environment",
        "status",
        "output_artifacts",
        "warnings",
        "errors",
        "decisions",
        "repair_history",
        "user_overrides",
        "lineage",
    )
    differences = []
    for field_name in fields:
        first = _json_safe(getattr(left, field_name))
        second = _json_safe(getattr(right, field_name))
        if first != second:
            differences.append(ManifestDifference(field_name, first, second))
    return tuple(differences)


# {
#   責務: [add_run_manifest_cli_commands: run show/replay/compare共通CLI subcommandsを登録する]
#   処理: [1: show/replay manifest path parserを作る 2: compare left/right ID parserを作る]
#   引数: [subparsers: argparse subcommand group]
#   戻り値: []
# }
def add_run_manifest_cli_commands(subparsers) -> None:
    run_parser = subparsers.add_parser("run", help="inspect and compare durable run manifests")
    commands = run_parser.add_subparsers(dest="run_command", required=True)
    for command in ("show", "replay"):
        child = commands.add_parser(command)
        child.add_argument("manifest", type=Path)
    compare = commands.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)


# {
#   責務: [run_manifest_cli_result: parsed run commandをJSON-safe show/replay/compare outputへ変換する]
#   処理: [1: manifest(s)をloadする 2: action別にview/replay/differencesを返す]
#   引数: [arguments: run CLI namespace]
#   戻り値: [result: JSON-compatible CLI result]
# }
def run_manifest_cli_result(arguments) -> dict:
    if arguments.run_command in {"show", "replay"}:
        manifest = _load_manifest_file(arguments.manifest)
        if arguments.run_command == "show":
            return run_manifest_to_dict(manifest)
        return _json_safe(manifest_replay_request(manifest))
    left = _load_manifest_file(arguments.left)
    right = _load_manifest_file(arguments.right)
    return {"differences": _json_safe(compare_run_manifests(left, right))}
