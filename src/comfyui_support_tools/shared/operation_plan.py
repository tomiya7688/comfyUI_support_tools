"""Common stale-safe operation planning, preview, and apply primitives."""

import argparse
import hashlib
import json
import math
import random
import stat
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from comfyui_support_tools.shared.contracts.operation_plan import (
    OperationMode,
    OperationPlan,
    OperationPreview,
    PlanExecutionResult,
    PlanExecutionStatus,
    PlannedAction,
    SourceSnapshot,
)
from comfyui_support_tools.shared.output_artifact import ConflictPolicy, atomic_write_bytes

PLAN_SCHEMA_VERSION = 1
MAX_PREVIEW_ACTIONS = 1000
CONTENT_HASH_LIMIT_BYTES = 8 * 1024 * 1024
CONFIRMATION_OPERATIONS = frozenset({"delete", "remove", "overwrite", "replace", "move", "rename"})


# {
#   責務: [capture_source_snapshot: source pathの現在fingerprintをplan向けに固定する]
#   処理: [1: lstat metadataを読む 2: small regular fileをhashする 3: missing pathも明示する]
#   引数: [source_id: stable caller ID, path: source filesystem path, content_hash_limit: hash上限byte数]
#   戻り値: [snapshot: stale plan比較用fingerprint]
# }
def capture_source_snapshot(
    source_id: str,
    path: Path,
    content_hash_limit: int = CONTENT_HASH_LIMIT_BYTES,
) -> SourceSnapshot:
    if not source_id.strip() or content_hash_limit < 0:
        raise ValueError("source ID and nonnegative content hash limit are required")
    source = Path(path).expanduser().absolute()
    try:
        metadata = source.lstat()
    except FileNotFoundError:
        return SourceSnapshot(source_id, str(source), False, 0, 0, 0, 0, 0)
    digest = ""
    if stat.S_ISREG(metadata.st_mode) and metadata.st_size <= content_hash_limit:
        hasher = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
    return SourceSnapshot(
        source_id,
        str(source),
        True,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_mode,
        metadata.st_dev,
        metadata.st_ino,
        digest,
    )


# {
#   責務: [settings_digest: JSON-safe settingsをcanonical SHA-256へ正規化する]
#   処理: [1: key順固定JSONを生成する 2: UTF-8 bytesのSHA-256を返す]
#   引数: [settings: operation-specific immutable settings mapping]
#   戻り値: [digest: same settingsのstable fingerprint]
# }
def settings_digest(settings: Mapping) -> str:
    try:
        encoded = json.dumps(
            settings,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("settings must be finite JSON-compatible values") from error
    return hashlib.sha256(encoded).hexdigest()


# {
#   責務: [create_operation_plan: source/action/settingsから共通OperationPlanを作る]
#   処理: [1: identity/count/actionを検証する 2: sourcesをfingerprintする 3: digest/count/reversibilityを集計する]
#   引数: [operation_id: stable ID, mode: operation mode, sources: id/path pairs, actions: proposals, settings: settings snapshot, skipped_count/warnings/conflicts/resources/before_after]
#   戻り値: [plan: immutable OperationPlan]
# }
def create_operation_plan(
    operation_id: str,
    mode: OperationMode | str,
    sources: Mapping[str, Path],
    actions: Sequence[PlannedAction],
    settings: Mapping,
    *,
    skipped_count: int = 0,
    warnings: Sequence[str] = (),
    conflicts: Sequence[str] = (),
    estimated_resources: Mapping[str, int | float | str] | None = None,
    output_destinations: Sequence[str] = (),
    decision_reasons: Sequence[str] = (),
    confidence: float = 1.0,
    before_count: int | None = None,
    after_count: int | None = None,
) -> OperationPlan:
    if not operation_id.strip() or type(skipped_count) is not int or skipped_count < 0:
        raise ValueError("operation ID and nonnegative skipped count are required")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be finite and in 0..1")
    source_items = tuple(
        capture_source_snapshot(source_id, path) for source_id, path in sources.items()
    )
    source_ids = {item.source_id for item in source_items}
    action_items = tuple(actions)
    if len(source_ids) != len(source_items):
        raise ValueError("source IDs must be unique")
    if len({item.action_id for item in action_items}) != len(action_items):
        raise ValueError("action IDs must be unique")
    if any(not item.action_id.strip() or not item.operation.strip() for item in action_items):
        raise ValueError("action IDs and operations must not be empty")
    if any(item.source_id not in source_ids for item in action_items):
        raise ValueError("every action must reference a planned source")
    if any(not isinstance(item.decision_reasons, tuple) for item in action_items):
        raise ValueError("action decision reasons must be tuples")
    if any(
        not math.isfinite(item.confidence) or not 0 <= item.confidence <= 1 for item in action_items
    ):
        raise ValueError("action confidence must be finite and in 0..1")
    resources = tuple(sorted((estimated_resources or {}).items()))
    if any(isinstance(value, float) and not math.isfinite(value) for _, value in resources):
        raise ValueError("estimated resources must be finite")
    before = len(source_items) if before_count is None else before_count
    after = max(0, before - len(action_items)) if after_count is None else after_count
    if type(before) is not int or type(after) is not int or before < 0 or after < 0:
        raise ValueError("before/after counts must be nonnegative integers")
    return OperationPlan(
        operation_id,
        OperationMode(mode),
        source_items,
        action_items,
        len(action_items),
        skipped_count,
        before,
        after,
        tuple(str(value)[:500] for value in warnings),
        tuple(str(value)[:500] for value in conflicts),
        resources,
        tuple(dict.fromkeys(str(value)[:4096] for value in output_destinations)),
        tuple(str(value)[:300] for value in decision_reasons),
        all(item.reversible for item in action_items),
        confidence,
        settings_digest(settings),
        time.time(),
        PLAN_SCHEMA_VERSION,
    )


# {
#   責務: [preview_operation_plan: high-risk/reason/random representative sampleを選ぶ]
#   処理: [1: risk優先で選ぶ 2: reasonごと代表を追加する 3: seeded randomで残枠を埋める]
#   引数: [plan: operation plan, sample_limit: preview上限, seed: preview sample seed]
#   戻り値: [preview: selected samplesとreason/count distribution]
# }
def preview_operation_plan(
    plan: OperationPlan,
    sample_limit: int = 24,
    seed: int = 0,
) -> OperationPreview:
    if type(sample_limit) is not int or not 0 <= sample_limit <= MAX_PREVIEW_ACTIONS:
        raise ValueError("sample_limit must be in 0..1000")
    actions = plan.proposed_actions
    selected: list[PlannedAction] = []
    selected_ids = set()
    for action in actions:
        if action.risk_level.casefold() in {"high", "critical"} and len(selected) < sample_limit:
            selected.append(action)
            selected_ids.add(action.action_id)
    reasons: dict[str, list[PlannedAction]] = {}
    for action in actions:
        for reason in action.decision_reasons:
            reasons.setdefault(reason, []).append(action)
    for reason in sorted(reasons):
        if len(selected) >= sample_limit:
            break
        representative = next(
            (item for item in reasons[reason] if item.action_id not in selected_ids), None
        )
        if representative is not None:
            selected.append(representative)
            selected_ids.add(representative.action_id)
    remaining = [item for item in actions if item.action_id not in selected_ids]
    amount = min(sample_limit - len(selected), len(remaining))
    if amount:
        selected.extend(random.Random(seed).sample(remaining, amount))
    distribution = Counter(reason for item in actions for reason in item.decision_reasons)
    return OperationPreview(
        tuple(selected),
        plan.affected_count,
        plan.skipped_count,
        sum(item.review_required for item in actions),
        plan.before_count,
        plan.after_count,
        tuple(sorted(distribution.items())),
    )


# {
#   責務: [save_operation_plan: planとintegrity digestをatomic JSON manifestへ保存する]
#   処理: [1: canonical plan documentを作る 2: digestを付ける 3: shared artifact transactionでatomic writeする]
#   引数: [plan: operation plan, path: manifest destination, overwrite: replace existing manifest flag]
#   戻り値: [written_path: saved manifest path]
# }
def save_operation_plan(plan: OperationPlan, path: Path, *, overwrite: bool = False) -> Path:
    payload = operation_plan_to_dict(plan)
    encoded_plan = _canonical_json(payload)
    envelope = {
        "plan": payload,
        "plan_sha256": hashlib.sha256(encoded_plan).hexdigest(),
    }
    target = Path(path)
    atomic_write_bytes(
        target,
        _canonical_json(envelope) + b"\n",
        policy=ConflictPolicy.OVERWRITE if overwrite else ConflictPolicy.FAIL,
        validator=lambda staged: load_operation_plan(staged),
    )
    return target


# {
#   責務: [load_operation_plan: versioned plan JSONとsha256 envelopeを検証して復元する]
#   処理: [1: JSON envelopeを読む 2: digest/schemaを確認する 3: dataclass contractへ復元する]
#   引数: [path: saved plan path]
#   戻り値: [plan: validated immutable plan]
# }
def load_operation_plan(path: Path) -> OperationPlan:
    try:
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
        payload = envelope["plan"]
        digest = envelope["plan_sha256"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        raise ValueError("operation plan manifest cannot be read") from error
    if not isinstance(payload, dict) or not isinstance(digest, str):
        raise ValueError("operation plan manifest has an invalid envelope")
    actual_digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if actual_digest != digest:
        raise ValueError("operation plan manifest digest does not match")
    if payload.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError("operation plan schema version is unsupported")
    try:
        return OperationPlan(
            operation_id=payload["operation_id"],
            mode=OperationMode(payload["mode"]),
            source_items=tuple(SourceSnapshot(**item) for item in payload["source_items"]),
            proposed_actions=tuple(
                PlannedAction(
                    **{**item, "decision_reasons": tuple(item.get("decision_reasons", ()))}
                )
                for item in payload["proposed_actions"]
            ),
            affected_count=payload["affected_count"],
            skipped_count=payload["skipped_count"],
            before_count=payload["before_count"],
            after_count=payload["after_count"],
            warnings=tuple(payload["warnings"]),
            conflicts=tuple(payload["conflicts"]),
            estimated_resources=tuple(tuple(item) for item in payload["estimated_resources"]),
            output_destinations=tuple(payload["output_destinations"]),
            decision_reasons=tuple(payload["decision_reasons"]),
            reversible=payload["reversible"],
            confidence=payload["confidence"],
            settings_sha256=payload["settings_sha256"],
            created_at=payload["created_at"],
            schema_version=payload["schema_version"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("operation plan payload is invalid") from error


# {
#   責務: [operation_plan_to_dict: immutable OperationPlanをversioned JSON-safe objectへ変換する]
#   処理: [1: nested dataclassをdictへ展開する 2: Enum modeをstable stringへ置換する]
#   引数: [plan: operation plan]
#   戻り値: [payload: canonical JSON-compatible mapping]
# }
def operation_plan_to_dict(plan: OperationPlan) -> dict:
    payload = asdict(plan)
    payload["mode"] = plan.mode.value
    return payload


# {
#   責務: [apply_operation_plan: source/settings/decisionを再検証後にだけmutation callbackを実行する]
#   処理: [1: manifest-only/stale/confirmationを検査する 2: same plannerを再実行しdecisionを比較する 3: actionを順にapplyする]
#   引数: [plan: stored plan, current_settings: live settings, rebuild_plan: same decision logic callback, apply_action: mutation callback, confirmed: high-risk confirmation, rollback_action: optional reverse callback]
#   戻り値: [result: applied/stale/review/failed status]
# }
def apply_operation_plan(
    plan: OperationPlan,
    current_settings: Mapping,
    rebuild_plan: Callable[[], OperationPlan],
    apply_action: Callable[[PlannedAction], None],
    *,
    confirmed: bool = False,
    rollback_action: Callable[[PlannedAction], None] | None = None,
) -> PlanExecutionResult:
    if plan.mode is OperationMode.MANIFEST_ONLY:
        return PlanExecutionResult(PlanExecutionStatus.MANIFEST_ONLY)
    if plan.conflicts:
        return PlanExecutionResult(
            PlanExecutionStatus.BLOCKED_CONFLICT,
            message=f"plan contains {len(plan.conflicts)} unresolved conflict(s)",
        )
    try:
        if settings_digest(current_settings) != plan.settings_sha256:
            return PlanExecutionResult(PlanExecutionStatus.STALE_SETTINGS)
    except ValueError as error:
        return PlanExecutionResult(PlanExecutionStatus.STALE_SETTINGS, message=str(error))
    if not _sources_are_current(plan.source_items):
        return PlanExecutionResult(PlanExecutionStatus.STALE_SOURCE)
    if not callable(rebuild_plan) or not callable(apply_action):
        raise TypeError("rebuild_plan and apply_action must be callable")
    try:
        refreshed = rebuild_plan()
    except Exception as error:
        return PlanExecutionResult(
            PlanExecutionStatus.STALE_DECISIONS,
            message=f"plan recomputation failed: {type(error).__name__}",
        )
    if _decision_fingerprint(refreshed) != _decision_fingerprint(plan):
        return PlanExecutionResult(PlanExecutionStatus.STALE_DECISIONS)
    if not _sources_are_current(plan.source_items):
        return PlanExecutionResult(PlanExecutionStatus.STALE_SOURCE)
    needs_confirmation = any(
        action.review_required
        or action.risk_level.casefold() in {"high", "critical"}
        or action.operation.casefold() in CONFIRMATION_OPERATIONS
        for action in plan.proposed_actions
    )
    if needs_confirmation and not confirmed:
        return PlanExecutionResult(PlanExecutionStatus.CONFIRMATION_REQUIRED)
    applied: list[PlannedAction] = []
    try:
        for action in plan.proposed_actions:
            apply_action(action)
            applied.append(action)
    except Exception as error:
        rollback_message = ""
        if rollback_action is not None and plan.reversible:
            try:
                for action in reversed(applied):
                    rollback_action(action)
                rollback_message = "; completed actions rolled back"
            except Exception as rollback_error:
                rollback_message = f"; rollback failed: {type(rollback_error).__name__}"
        return PlanExecutionResult(
            PlanExecutionStatus.FAILED,
            len(applied),
            f"apply failed: {type(error).__name__}{rollback_message}",
        )
    return PlanExecutionResult(PlanExecutionStatus.APPLIED, len(applied))


# {
#   責務: [_sources_are_current: current path fingerprintsがplan source snapshotと同じか確認する]
#   処理: [1: 各sourceを再stat/hashする 2: missing/changed/errorsをstaleとして返す]
#   引数: [sources: captured source snapshots]
#   戻り値: [current: 全sourceが一致した場合true]
# }
def _sources_are_current(sources: Sequence[SourceSnapshot]) -> bool:
    try:
        return all(
            capture_source_snapshot(item.source_id, Path(item.path)) == item for item in sources
        )
    except (OSError, ValueError):
        return False


# {
#   責務: [_decision_fingerprint: timestampを除いたplan decisionsのstable digestを作る]
#   処理: [1: settings/source/action/count/resource fieldsを選ぶ 2: canonical JSON digestを返す]
#   引数: [plan: operation plan]
#   戻り値: [digest: decision-equivalence hash]
# }
def _decision_fingerprint(plan: OperationPlan) -> str:
    payload = operation_plan_to_dict(plan)
    payload.pop("created_at", None)
    payload.pop("mode", None)
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


# {
#   責務: [OperationCliOptions: common CLI mode/plan flagsを保持する]
#   フィールド: [mode、plan output、apply plan、preview sample limit]
# }
@dataclass(frozen=True)
class OperationCliOptions:
    mode: OperationMode
    plan_out: Path | None
    apply_plan: Path | None
    preview_sample: int


# {
#   責務: [add_operation_cli_arguments: parserへ共通dry-run/plan/apply flagsを登録する]
#   処理: [1: mutually-exclusive mode flagsを追加する 2: plan output/preview sampleを登録する]
#   引数: [parser: application-specific argparse parser]
#   戻り値: []
# }
def add_operation_cli_arguments(parser: argparse.ArgumentParser) -> None:
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--dry-run", action="store_true", help="analyze and print a safe operation plan"
    )
    modes.add_argument(
        "--apply-plan", type=Path, help="revalidate and apply a saved operation plan"
    )
    modes.add_argument(
        "--manifest-only", action="store_true", help="write the plan without applying it"
    )
    parser.add_argument("--plan-out", type=Path, help="write the generated plan to this JSON path")
    parser.add_argument(
        "--preview-sample",
        type=int,
        default=0,
        help="show at most N representative/high-risk action samples",
    )


# {
#   責務: [resolve_operation_cli_options: parsed flagsを共通OperationModeへ変換する]
#   処理: [1: incompatible preview/apply combinationsを拒否する 2: requested mode/output pathsを決める]
#   引数: [arguments: argparse Namespace]
#   戻り値: [options: normalized CLI operation options]
# }
def resolve_operation_cli_options(arguments) -> OperationCliOptions:
    preview_count = getattr(arguments, "preview_sample", 0)
    if type(preview_count) is not int or not 0 <= preview_count <= MAX_PREVIEW_ACTIONS:
        raise ValueError("--preview-sample must be in 0..1000")
    apply_path = getattr(arguments, "apply_plan", None)
    dry_run = bool(getattr(arguments, "dry_run", False))
    manifest_only = bool(getattr(arguments, "manifest_only", False))
    if apply_path is not None and preview_count:
        raise ValueError("--preview-sample cannot be combined with --apply-plan")
    if dry_run:
        mode = OperationMode.PREVIEW_SAMPLE if preview_count else OperationMode.DRY_RUN
    elif apply_path is not None:
        mode = OperationMode.APPLY_WITH_REVIEW
    elif manifest_only:
        mode = OperationMode.MANIFEST_ONLY
    elif preview_count:
        mode = OperationMode.PREVIEW_SAMPLE
    else:
        mode = OperationMode.APPLY
    return OperationCliOptions(
        mode,
        getattr(arguments, "plan_out", None),
        apply_path,
        preview_count,
    )


# {
#   責務: [_canonical_json: JSON objectをdeterministic UTF-8 bytesへencodeする]
#   処理: [1: key orderとseparatorを固定する 2: NaNを拒否する]
#   引数: [value: JSON-compatible payload]
#   戻り値: [encoded: canonical JSON bytes]
# }
def _canonical_json(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
