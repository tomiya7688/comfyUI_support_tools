"""Registry for installed model families and declarative generation capabilities."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .contracts import GenerationCapability


# {
#   責務: [CapabilityRegistry: immutable generation capability descriptorsをIDとaliasで管理する]
#   フィールド: [profile_id map]
#   処理: [new model familiesをrouter algorithm変更なしで追加できるregistryを提供する]
# }
class CapabilityRegistry:
    # {
    #   責務: [__init__: ID重複を防ぎdescriptorをprofile ID順に保存する]
    #   処理: [materialize validated profiles into a case-insensitive unique-ID map]
    #   引数: [capabilities: built-in or user-provided profile rows]
    #   戻り値: []
    # }
    def __init__(self, capabilities: Iterable[GenerationCapability]) -> None:
        self._profiles: dict[str, GenerationCapability] = {}
        for capability in capabilities:
            if not isinstance(capability, GenerationCapability):
                raise TypeError("registry entries must be GenerationCapability values")
            key = capability.profile_id.casefold()
            if key in self._profiles:
                raise ValueError(f"duplicate generation capability: {capability.profile_id}")
            self._profiles[key] = capability

    # {
    #   責務: [profiles: registration orderでimmutableなdescriptor snapshotを返す]
    #   処理: [expose the registry as an immutable tuple]
    #   引数: [self: capability registry]
    #   戻り値: [tuple[GenerationCapability, ...]: declared profiles]
    # }
    @property
    def profiles(self) -> tuple[GenerationCapability, ...]:
        return tuple(self._profiles.values())

    # {
    #   責務: [get: stable profile IDで一件のdescriptorを取得する]
    #   処理: [look up one ID without changing registration state]
    #   引数: [self: registry, profile_id: case-insensitive identifier]
    #   戻り値: [GenerationCapability | None: matching descriptor]
    # }
    def get(self, profile_id: str) -> GenerationCapability | None:
        return self._profiles.get(profile_id.casefold())

    # {
    #   責務: [classify: installed local model nameから最も具体的なcapabilityを解決する]
    #   処理: [normalize identity, prefer longest alias, and reject equal-specificity ambiguity]
    #   処理: [token-boundary alias matchを行い, 同じ具体性の衝突はunknownにする]
    #   引数: [self: registry, model_name: installed model identifier/path]
    #   戻り値: [GenerationCapability | None: unambiguous descriptor]
    # }
    def classify(self, model_name: str) -> GenerationCapability | None:
        normalized = _normalize(model_name)
        if not normalized:
            return None
        matches = [
            (len(_normalize(alias)), profile)
            for profile in self._profiles.values()
            for alias in profile.aliases
            if _contains_alias(normalized, _normalize(alias))
        ]
        if not matches:
            return None
        specificity = max(length for length, _profile in matches)
        profiles = {
            profile.profile_id: profile for length, profile in matches if length == specificity
        }
        return next(iter(profiles.values())) if len(profiles) == 1 else None


# {
#   責務: [_normalize: installed model pathをcase-folded token textにする]
#   処理: [replace punctuation runs and trim normalized whitespace]
#   引数: [value: model filename or profile alias]
#   戻り値: [str: punctuation-separated normalized model identity]
# }
def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


# {
#   責務: [_contains_alias: model identity内でaliasをtoken boundary付き照合する]
#   処理: [match aliases only on complete token boundaries]
#   引数: [model_name: normalized installed model name, alias: normalized alias]
#   戻り値: [bool: alias matches complete tokens]
# }
def _contains_alias(model_name: str, alias: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", model_name) is not None
