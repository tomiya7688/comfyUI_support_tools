"""Field-level privacy transformations for run manifest values."""

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace

from comfyui_support_tools.shared.contracts.run_manifest import (
    ArtifactReference,
    PrivacyMode,
    RunDecision,
)
from comfyui_support_tools.shared.run_manifest_codec import _canonical_json, _json_safe


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
