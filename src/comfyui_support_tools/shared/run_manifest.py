"""Versioned run provenance, privacy filtering, replay, and durable stores."""

import hashlib
import json
import os
import secrets
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from enum import Enum
from pathlib import Path
from typing import Protocol

from comfyui_support_tools.shared.contracts.run_manifest import (
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

RUN_MANIFEST_SCHEMA_VERSION = 1


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
        target = self.root / f"{_safe_run_id(manifest.run_id)}.json"
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic_write_bytes(
                target,
                _canonical_json(envelope) + b"\n",
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
        if not event.run_id or type(event.sequence) is not int or event.sequence < 0:
            raise ValueError("event run ID and nonnegative sequence are required")
        if not event.event_type.strip():
            raise ValueError("event type is required")
        path = self.root / f"{_safe_run_id(event.run_id)}.jsonl"
        data = _canonical_json(asdict(event)) + b"\n"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._lock:
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
            records = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
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
    started_at: float | None = None,
) -> RunManifest:
    if not application_id.strip() or not settings_schema_version.strip():
        raise ValueError("application ID and settings schema version are required")
    privacy = tuple(
        sorted((key, PrivacyMode(value)) for key, value in (privacy_modes or {}).items())
    )
    modes = dict(privacy)
    secure_inputs = tuple(_secure_artifact(item, modes) for item in input_refs)
    secure_settings = _secure_mapping("settings", resolved_settings or {}, modes)
    secure_environment = _secure_mapping("environment", environment or {}, modes)
    secure_overrides = _secure_mapping("user_overrides", user_overrides or {}, modes)
    secure_provenance = _secure_mapping("provenance", provenance or {}, modes)
    seeds = tuple(
        sorted((str(key), _validate_seed(value)) for key, value in (random_seeds or {}).items())
    )
    selections = _secure_mapping("random_selections", random_selections or {}, modes)
    now = time.time() if started_at is None else float(started_at)
    return RunManifest(
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
        schema_version=RUN_MANIFEST_SCHEMA_VERSION,
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
    source = Path(path).expanduser().absolute()
    metadata = source.stat()
    if hash_limit_bytes < 0:
        raise ValueError("hash limit must be nonnegative")
    digest = ""
    if hash_content and source.is_file() and metadata.st_size <= hash_limit_bytes:
        hasher = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    return ArtifactReference(
        artifact_id or source.name,
        str(source),
        metadata.st_size if source.is_file() else None,
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
    modes = {key: PrivacyMode(value) for key, value in (privacy_modes or {}).items()}
    return RunManifestEvent(
        run_id,
        sequence,
        time.time() if created_at is None else float(created_at),
        event_type,
        _secure_mapping("event", payload or {}, modes),
    )


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
    terminal = RunStatus(status)
    if terminal is RunStatus.RUNNING:
        raise ValueError("finished manifest must have a terminal status")
    privacy = dict(manifest.privacy_modes)
    candidate_mode = privacy.get("candidate_ref", PrivacyMode.FULL)
    return replace(
        manifest,
        status=terminal,
        finished_at=time.time() if finished_at is None else float(finished_at),
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
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
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
            random_seeds=tuple(
                (str(key), _validate_seed(value)) for key, value in payload.get("random_seeds", ())
            ),
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
            schema_version=payload["schema_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("run manifest schema payload is invalid") from error
    _validate_manifest(manifest)
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
    if manifest.schema_version != RUN_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported run manifest schema version")
    if not manifest.run_id or not manifest.application_id or not manifest.settings_schema_version:
        raise ValueError("run ID, application ID, and settings schema version are required")
    if manifest.started_at < 0 or (
        manifest.finished_at is not None and manifest.finished_at < manifest.started_at
    ):
        raise ValueError("run timestamps are invalid")
    if manifest.status is RunStatus.RUNNING and manifest.finished_at is not None:
        raise ValueError("running manifest cannot have a finish time")
    if manifest.status is not RunStatus.RUNNING and manifest.finished_at is None:
        raise ValueError("terminal manifest requires a finish time")
    for _key, seed in manifest.random_seeds:
        _validate_seed(seed)
    _canonical_json(run_manifest_to_dict(manifest))


# {
#   責務: [_secure_artifact: privacy policyに従ってartifact locator/hashを保存する]
#   処理: [1: URI privacyを適用する 2: size/hash/media timing metadataを保持またはfilterする]
#   引数: [artifact: input/output artifact, modes: field privacy modes]
#   戻り値: [secured: privacy-filtered ref]
# }
def _secure_artifact(artifact: ArtifactReference, modes: Mapping[str, PrivacyMode]):
    uri_mode = modes.get("artifact_uri", PrivacyMode.FULL)
    id_mode = modes.get("artifact_id", PrivacyMode.FULL)
    hash_mode = modes.get("artifact_hash", PrivacyMode.FULL)
    return replace(
        artifact,
        artifact_id=_secure_locator(artifact.artifact_id, id_mode),
        uri=_secure_locator(artifact.uri, uri_mode),
        sha256=_secure_locator(artifact.sha256, hash_mode) if artifact.sha256 else "",
        media_timing=_secure_mapping("media_timing", dict(artifact.media_timing), modes),
    )


# {
#   責務: [_secure_decision: decision reason/details/candidate refsへprivacy policyを適用する]
#   処理: [1: reason/ref field modesを適用する 2: detail mappingをfilterする]
#   引数: [decision: candidate decision, modes: privacy modes]
#   戻り値: [secured: filtered decision]
# }
def _secure_decision(decision: RunDecision, modes: Mapping[str, PrivacyMode]):
    reason_mode = modes.get("decision_reason", PrivacyMode.FULL)
    candidate_mode = modes.get("candidate_ref", PrivacyMode.FULL)
    return replace(
        decision,
        reason=_secure_value(decision.reason, reason_mode),
        candidate_ref=_secure_value(decision.candidate_ref, candidate_mode),
        details=_secure_mapping("decision_details", dict(decision.details), modes),
    )


# {
#   責務: [_secure_mapping: field category/key privacy policyでmappingを保存可能値へ変換する]
#   処理: [1: category/key-specific modeを解決する 2: none fieldsをdropし他modeでfilterする]
#   引数: [category: privacy policy scope, values: input mapping, modes: policy map]
#   戻り値: [secure values: immutable key/value pairs]
# }
def _secure_mapping(category: str, values: Mapping, modes: Mapping[str, PrivacyMode]):
    secured = []
    category_mode = modes.get(category, PrivacyMode.FULL)
    for key, value in values.items():
        field_mode = modes.get(f"{category}.{key}", category_mode)
        if field_mode is PrivacyMode.NONE:
            continue
        secured.append((str(key), _secure_value(value, field_mode)))
    return tuple(sorted(secured))


# {
#   責務: [_secure_value: full/hash/summary/none privacy ruleをJSON-safe valueへ適用する]
#   処理: [1: none/hash/summary modeを処理する 2: full valuesのJSON compatibilityを確認する]
#   引数: [value: value to protect, mode: privacy mode]
#   戻り値: [safe value or digest/summary]
# }
def _secure_value(value, mode: PrivacyMode):
    if mode is PrivacyMode.NONE:
        return None
    safe = _json_safe(value)
    encoded = _canonical_json(safe)
    if mode is PrivacyMode.HASH:
        return {"sha256": hashlib.sha256(encoded).hexdigest()}
    if mode is PrivacyMode.SUMMARY:
        if isinstance(value, str):
            return value[:160]
        return {"type": type(value).__name__, "json_bytes": len(encoded)}
    return safe


# {
#   責務: [_secure_locator: URI/path privacy resultをtyped stable locator stringへ正規化する]
#   処理: [1: full/summary/hash/none modeを適用する 2: redacted locatorを返す]
#   引数: [value: source URI, mode: privacy mode]
#   戻り値: [locator: safe string]
# }
def _secure_locator(value: str, mode: PrivacyMode) -> str:
    if mode is PrivacyMode.NONE:
        return ""
    if mode is PrivacyMode.HASH:
        return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()
    if mode is PrivacyMode.SUMMARY:
        return value[:160]
    return value


# {
#   責務: [_secure_strings: warning/error text listへprivacy modeとlength limitを適用する]
#   処理: [1: none itemを省く 2: hash/summary/full textをbounded tupleへ変換する]
#   引数: [values: text sequence, mode: privacy setting, limit: maximum character count]
#   戻り値: [messages: privacy-filtered text]
# }
def _secure_strings(values: Sequence[str], mode: PrivacyMode, limit: int) -> tuple[str, ...]:
    if mode is PrivacyMode.NONE:
        return ()
    return tuple(_secure_locator(str(value)[:limit], mode) for value in values)


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
    if not run_id or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in run_id
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
