"""Deterministic semantic target normalization before model-based grounding."""

import re
import unicodedata
from dataclasses import dataclass, replace

from comfyui_support_tools.shared.semantic_erase.contracts import (
    EraseTargetType,
    FillPolicy,
    SemanticEraseTarget,
)

_PREFIX = re.compile(
    r"^(?:please\s+)?(?:remove|erase|delete|clean(?:\s+up)?|get\s+rid\s+of)\s+(?:only\s+)?",
    re.IGNORECASE,
)
_FILL = re.compile(r"(?:\bfill\s*:\s*|\bfill with\s+)(.+)$", re.IGNORECASE)
_SCOPE = re.compile(r"\b(?:on|from|near|in|around|within|at)\s+(.+)$", re.IGNORECASE)
_TAXONOMY = (
    ("background person", "person", EraseTargetType.OBJECT),
    ("blood stain", "blood stain", EraseTargetType.ATTRIBUTE),
    ("clothing damage", "clothing damage", EraseTargetType.STATE),
    ("unwanted artifact", "artifact", EraseTargetType.ARTIFACT),
    ("glasses", "glasses", EraseTargetType.OBJECT),
    ("accessory", "accessory", EraseTargetType.OBJECT),
    ("bruise", "bruise", EraseTargetType.ATTRIBUTE),
    ("scratch", "scratch", EraseTargetType.ATTRIBUTE),
    ("blood", "blood", EraseTargetType.ATTRIBUTE),
    ("tear", "tear", EraseTargetType.STATE),
    ("tears", "tear", EraseTargetType.STATE),
    ("sweat", "sweat", EraseTargetType.STATE),
    ("blush", "blush", EraseTargetType.STATE),
    ("stain", "stain", EraseTargetType.ATTRIBUTE),
    ("dirt", "dirt", EraseTargetType.ATTRIBUTE),
    ("scar", "scar", EraseTargetType.MARK),
    ("logo", "logo", EraseTargetType.TEXT),
    ("text", "text", EraseTargetType.TEXT),
    ("mark", "mark", EraseTargetType.MARK),
    ("artifact", "artifact", EraseTargetType.ARTIFACT),
    ("傷", "傷", EraseTargetType.ATTRIBUTE),
    ("あざ", "あざ", EraseTargetType.ATTRIBUTE),
    ("血", "血", EraseTargetType.ATTRIBUTE),
    ("涙", "涙", EraseTargetType.STATE),
    ("汗", "汗", EraseTargetType.STATE),
    ("汚れ", "汚れ", EraseTargetType.ATTRIBUTE),
    ("ロゴ", "ロゴ", EraseTargetType.TEXT),
    ("文字", "文字", EraseTargetType.TEXT),
    ("不要物", "不要物", EraseTargetType.OBJECT),
)


# {
# 責務: [ResolvedSemanticQuery: normalized tagと自然文scopeを分けて返す]
# フィールド: [original,normalized_tag,provider_query,target_type,range_label,fill_instruction]
# }
@dataclass(frozen=True)
class ResolvedSemanticQuery:
    original: str
    normalized_tag: str
    provider_query: str
    target_type: EraseTargetType
    range_label: str | None
    fill_instruction: str | None


# {
# 責務: [resolve_semantic_query: natural-language instructionをgrounding contractへ正規化する]
# 処理: [1: unicode/leading actionをnormalizeする, 2: known target synonymをresolveする, 3: scope/fill phraseを分離する]
# 引数: [query: user instruction, fallback_type: user-selected target type]
# 戻り値: [resolved: provider-ready semantic query]
# }
def resolve_semantic_query(
    query: str, fallback_type: EraseTargetType = EraseTargetType.OBJECT
) -> ResolvedSemanticQuery:
    normalized = unicodedata.normalize("NFKC", query).strip()
    fill_instruction = None
    fill_match = _FILL.search(normalized)
    if fill_match:
        fill_instruction = fill_match.group(1).strip()
        normalized = normalized[: fill_match.start()].strip(" ,.;")
    normalized = _PREFIX.sub("", normalized).strip(" ,.;")
    scope_label = None
    scope_match = _SCOPE.search(normalized)
    if scope_match:
        scope_label = scope_match.group(1).strip(" ,.;")
        normalized = normalized[: scope_match.start()].strip(" ,.;")
    folded = normalized.casefold()
    target_tag = normalized or query.strip()
    target_type = fallback_type
    for alias, canonical, inferred_type in _TAXONOMY:
        if alias.casefold() in folded:
            target_tag = canonical
            target_type = inferred_type
            break
    provider_query = f"{target_tag} {scope_label}".strip() if scope_label else target_tag
    return ResolvedSemanticQuery(
        query, target_tag, provider_query, target_type, scope_label, fill_instruction
    )


# {
# 責務: [resolve_target: SemanticEraseTargetへnormalized tag/scopeを適用する]
# 処理: [1: natural-language queryをparseする, 2: missing fieldsだけを埋めてimmutable targetを返す]
# 引数: [target: user erase request]
# 戻り値: [resolved: provider-ready immutable target]
# }
def resolve_target(target: SemanticEraseTarget) -> SemanticEraseTarget:
    result = resolve_semantic_query(target.query, target.target_type)
    fill_policy = target.fill_policy
    fill_instruction = target.fill_instruction
    if fill_instruction is None and result.fill_instruction:
        fill_instruction = result.fill_instruction
        fill_policy = FillPolicy.CUSTOM
    return replace(
        target,
        normalized_tag=target.normalized_tag or result.normalized_tag,
        provider_query=target.provider_query or result.provider_query,
        range_label=target.range_label or result.range_label,
        target_type=result.target_type,
        fill_instruction=fill_instruction,
        fill_policy=fill_policy,
    )
