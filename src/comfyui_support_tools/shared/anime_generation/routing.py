"""Declarative model-family registry and compatibility-first anime routing."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .contracts import (
    AnimeIntent,
    AnimeModelProfile,
    AnimeRouteRequest,
    AnimeRouteResult,
    AnimeRoutingError,
)


# {
#   責務: [AnimeModelRegistry: register model profile descriptors by ID and alias]
#   フィールド: [profile_id map, normalized alias map]
#   処理: [allow adding a family descriptor without modifying family inference or routing algorithms]
# }
class AnimeModelRegistry:
    # {
    #   責務: [__init__: validate a unique set of model profiles]
    #   処理: [index profile IDs and reject duplicate IDs or aliases]
    #   引数: [profiles: iterable of declarative model profiles]
    #   戻り値: []
    # }
    def __init__(self, profiles: Iterable[AnimeModelProfile]) -> None:
        self._profiles: dict[str, AnimeModelProfile] = {}
        self._aliases: dict[str, AnimeModelProfile] = {}
        for profile in profiles:
            if not isinstance(profile, AnimeModelProfile):
                raise TypeError("registry entries must be AnimeModelProfile values")
            profile_key = profile.profile_id.casefold()
            if profile_key in self._profiles:
                raise ValueError(f"duplicate anime model profile: {profile.profile_id}")
            alias_keys = {_normalize(alias) for alias in profile.aliases}
            if any(alias in self._aliases for alias in alias_keys):
                raise ValueError(f"duplicate anime model alias in {profile.profile_id}")
            self._profiles[profile_key] = profile
            for alias in alias_keys:
                self._aliases[alias] = profile

    # {
    #   責務: [profiles: expose profiles in stable registration order]
    #   処理: [return an immutable tuple snapshot]
    #   引数: [self: model registry]
    #   戻り値: [tuple[AnimeModelProfile, ...]: profiles]
    # }
    @property
    def profiles(self) -> tuple[AnimeModelProfile, ...]:
        return tuple(self._profiles.values())

    # {
    #   責務: [get: resolve one profile by its stable identifier]
    #   処理: [perform case-insensitive profile ID lookup]
    #   引数: [self: model registry, profile_id: registered ID]
    #   戻り値: [AnimeModelProfile | None: found profile]
    # }
    def get(self, profile_id: str) -> AnimeModelProfile | None:
        return self._profiles.get(profile_id.casefold())

    # {
    #   責務: [classify: match an installed model name to one unique profile]
    #   処理: [match normalized alias boundaries and preserve ambiguity as unknown]
    #   引数: [self: model registry, model_name: local checkpoint name or path]
    #   戻り値: [AnimeModelProfile | None: unique profile match]
    # }
    def classify(self, model_name: str) -> AnimeModelProfile | None:
        normalized = _normalize(model_name)
        if not normalized:
            return None
        matches = {
            profile.profile_id: profile
            for alias, profile in self._aliases.items()
            if _contains_alias(normalized, alias)
        }
        return next(iter(matches.values())) if len(matches) == 1 else None


# {
#   責務: [classify_anime_model: classify one checkpoint through registered descriptors]
#   処理: [delegate model-name matching to the supplied registry]
#   引数: [registry: model profiles, model_name: checkpoint name]
#   戻り値: [AnimeModelProfile | None: unique registered match]
# }
def classify_anime_model(registry: AnimeModelRegistry, model_name: str) -> AnimeModelProfile | None:
    return registry.classify(model_name)


# {
#   責務: [route_anime_model: rank compatible available profiles by user constraints]
#   処理: [1: preserve explicit model choice, 2: enforce required LoRA family compatibility, 3: rank by declared intent support]
#   引数: [registry: profile registry, request: installed models and routing constraints]
#   戻り値: [AnimeRouteResult: selected model, alternatives and reason]
# }
def route_anime_model(registry: AnimeModelRegistry, request: AnimeRouteRequest) -> AnimeRouteResult:
    candidates = [(name, registry.classify(name)) for name in request.available_models]
    candidates = [(name, profile) for name, profile in candidates if profile is not None]
    if request.explicit_model is not None:
        selected = next(
            ((name, profile) for name, profile in candidates if name == request.explicit_model),
            None,
        )
        if selected is None:
            raise AnimeRoutingError("explicit model has no unique registered anime profile")
        compatible = [
            (name, profile)
            for name, profile in candidates
            if _supports_required_loras(profile, request)
        ]
        if not _supports_required_loras(selected[1], request):
            raise AnimeRoutingError(
                f"explicit model {selected[0]!r} is incompatible with a required LoRA family"
            )
        ranked = _rank_by_intent(compatible, request.intent)
        ranked_names = [selected[0], *(name for name, _profile in ranked if name != selected[0])]
        return AnimeRouteResult(
            selected[0],
            selected[1],
            tuple(dict.fromkeys(ranked_names)),
            "Honored the explicit model selection after validating required LoRA compatibility.",
        )

    compatible = [
        (name, profile)
        for name, profile in candidates
        if _supports_required_loras(profile, request)
    ]
    ranked = _rank_by_intent(compatible, request.intent)
    if not ranked:
        if request.required_loras:
            raise AnimeRoutingError(
                "no installed anime model profile supports every required LoRA family"
            )
        raise AnimeRoutingError("no installed model matches a registered anime profile")
    selected_name, selected_profile = ranked[0]
    return AnimeRouteResult(
        selected_name,
        selected_profile,
        tuple(name for name, _profile in ranked),
        _route_reason(selected_profile, request.intent, request.required_loras),
    )


# {
#   責務: [_supports_required_loras: check profile declarations against required adapters]
#   処理: [require every mandatory LoRA to intersect the profile's compatible family declarations]
#   引数: [profile: candidate model profile, request: intent and adapter constraints]
#   戻り値: [bool: all required families are supported]
# }
def _supports_required_loras(profile: AnimeModelProfile, request: AnimeRouteRequest) -> bool:
    return all(
        not requirement.required
        or bool(profile.lora_compatible_families & requirement.compatible_families)
        for requirement in request.required_loras
    )


# {
#   責務: [_rank_by_intent: rank profiles by declared use-case suitability]
#   処理: [place profiles that declare the requested intent before general fallbacks, preserving registration order]
#   引数: [candidates: model/profile pairs, intent: requested use case]
#   戻り値: [list: deterministic capability-based order, not a quality score]
# }
def _rank_by_intent(
    candidates: list[tuple[str, AnimeModelProfile]], intent: AnimeIntent
) -> list[tuple[str, AnimeModelProfile]]:
    return sorted(
        candidates,
        key=lambda item: (intent not in item[1].recommended_intents, item[1].profile_id.casefold()),
    )


# {
#   責務: [_route_reason: explain declared capability-based candidate selection]
#   処理: [report LoRA constraints first and otherwise state intent match or fallback]
#   引数: [profile: selected profile, intent: requested use case, loras: required adapters]
#   戻り値: [str: user-readable decision explanation]
# }
def _route_reason(profile: AnimeModelProfile, intent: AnimeIntent, loras: tuple) -> str:
    required_loras = tuple(item for item in loras if item.required)
    if required_loras:
        names = ", ".join(item.name for item in required_loras)
        return f"Selected {profile.family} because it declares compatibility with required LoRAs: {names}."
    if intent in profile.recommended_intents:
        return (
            f"Selected {profile.family} because its profile recommends the {intent.value} use case."
        )
    return f"Selected {profile.family} as the first registered profile; no benchmark quality ranking is claimed."


# {
#   責務: [_normalize: canonicalize model aliases for boundary matching]
#   処理: [case-fold and replace path/space separators with one normalized separator]
#   引数: [value: alias or checkpoint name]
#   戻り値: [str: normalized model identifier]
# }
def _normalize(value: str) -> str:
    split_camel_case = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    split_versions = re.sub(r"([a-zA-Z])([0-9])", r"\1 \2", split_camel_case)
    return re.sub(r"[^a-z0-9]+", " ", split_versions.casefold()).strip()


# {
#   責務: [_contains_alias: match an alias as complete normalized tokens]
#   処理: [reject partial-token collisions such as noobai matching a different word]
#   引数: [model_name: normalized name, alias: normalized alias]
#   戻り値: [bool: alias is present at token boundaries]
# }
def _contains_alias(model_name: str, alias: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", model_name) is not None
