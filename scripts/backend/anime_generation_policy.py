"""Application adapter for anime model routing and prompt-family policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from comfyui_support_tools.shared.anime_generation import (
    AnimeContentMode,
    AnimeIntent,
    AnimeLoraRequirement,
    AnimeModelProfile,
    AnimeModelRegistry,
    AnimeRouteRequest,
    AnimeRoutingError,
    apply_anime_prompt_policy,
    create_default_anime_model_registry,
    route_anime_model,
)

from .prompt_lora_compatibility import extract_lora_references


# {
#   責務: [AnimePromptResolution: store model-aware prompt and routing output]
#   フィールド: [checkpoint, positive/negative prompts, profile ID, reason]
#   処理: [make generation inputs and applied policy reviewable as one immutable result]
# }
@dataclass(frozen=True)
class AnimePromptResolution:
    checkpoint: str
    prompt: str
    negative_prompt: str
    profile_id: str | None
    reason: str


# {
#   責務: [resolve_anime_generation: route an anime model and apply its registered prompt policy]
#   処理: [1: keep manual checkpoint selection unless auto-route is enabled, 2: reject known incompatible LoRAs, 3: apply model-native prompts]
#   引数: [checkpoint: selected base model, prompt/negative_prompt: expanded prompt text, model_catalog: local models, intent/content: requested profile, auto_route: opt-in routing, registry: injectable profile registry]
#   戻り値: [AnimePromptResolution: resolved checkpoint and prompts]
# }
def resolve_anime_generation(
    checkpoint: str,
    prompt: str,
    negative_prompt: str,
    model_catalog: dict[str, list[str]],
    *,
    intent: AnimeIntent = AnimeIntent.GENERAL,
    content_mode: AnimeContentMode = AnimeContentMode.UNSPECIFIED,
    auto_route: bool = False,
    registry: AnimeModelRegistry | None = None,
) -> AnimePromptResolution:
    profile_registry = registry or create_default_anime_model_registry()
    lora_requirements = _lora_requirements(
        prompt,
        model_catalog.get("loras", []),
        profile_registry,
        require_known_families=auto_route,
    )
    selected_checkpoint = checkpoint
    reason = (
        "No registered anime model profile matched the selected checkpoint; prompt is unchanged."
    )
    if auto_route:
        available = tuple(
            dict.fromkeys([*model_catalog.get("checkpoints", []), *model_catalog.get("unets", [])])
        )
        route = route_anime_model(
            profile_registry,
            AnimeRouteRequest(available, intent=intent, required_loras=lora_requirements),
        )
        selected_checkpoint = route.selected_model
        selected_profile = route.profile
        reason = route.reason
    else:
        selected_profile = profile_registry.classify(checkpoint)
        if selected_profile is not None:
            _ensure_lora_compatibility(selected_profile, lora_requirements)
            reason = (
                f"Applied the {selected_profile.family} prompt policy to the explicit checkpoint."
            )
    if selected_profile is None:
        return AnimePromptResolution(checkpoint, prompt, negative_prompt, None, reason)
    expanded_prompt, expanded_negative = apply_anime_prompt_policy(
        selected_profile,
        prompt,
        negative_prompt,
        intent=intent,
        content_mode=content_mode,
    )
    return AnimePromptResolution(
        selected_checkpoint,
        expanded_prompt,
        expanded_negative,
        selected_profile.profile_id,
        reason,
    )


# {
#   責務: [_lora_requirements: infer known anime adapter family constraints from prompt and local catalog]
#   処理: [resolve references uniquely and reject ambiguous/unknown adapters only when auto routing needs evidence]
#   引数: [prompt: expanded user prompt, candidates: installed LoRA catalog, registry: profile registry]
#   戻り値: [tuple[AnimeLoraRequirement, ...]: family constraints for the router]
# }
def _lora_requirements(
    prompt: str,
    candidates: list[str],
    registry: AnimeModelRegistry,
    *,
    require_known_families: bool,
) -> tuple[AnimeLoraRequirement, ...]:
    requirements = []
    for reference in extract_lora_references(prompt):
        resolved = _resolve_lora(reference, candidates)
        profile = registry.classify(resolved) if resolved is not None else None
        if profile is None:
            if require_known_families:
                raise AnimeRoutingError(
                    f"cannot safely auto-route because LoRA family is unknown: {reference}"
                )
            continue
        requirements.append(
            AnimeLoraRequirement(
                reference,
                frozenset({profile.family}),
            )
        )
    return tuple(requirements)


# {
#   責務: [_ensure_lora_compatibility: reject known cross-family LoRAs on an explicit anime model]
#   処理: [check every mandatory known family against the selected model descriptor]
#   引数: [profile: explicit model profile, requirements: prompt LoRA constraints]
#   戻り値: []
# }
def _ensure_lora_compatibility(
    profile: AnimeModelProfile, requirements: tuple[AnimeLoraRequirement, ...]
) -> None:
    incompatible = [
        item.name
        for item in requirements
        if item.required
        and not profile.lora_compatible_families.intersection(item.compatible_families)
    ]
    if incompatible:
        names = ", ".join(incompatible)
        raise AnimeRoutingError(f"LoRA family incompatible with {profile.family}: {names}")


# {
#   責務: [_resolve_lora: map one prompt reference to a unique catalog entry]
#   処理: [compare extensionless case-folded full names then unique basenames]
#   引数: [reference: prompt LoRA ID, candidates: local catalog entries]
#   戻り値: [str | None: unique installed adapter path]
# }
def _resolve_lora(reference: str, candidates: list[str]) -> str | None:
    requested = _normalize_lora(reference)
    exact = [name for name in candidates if _normalize_lora(name) == requested]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    requested_base = PurePosixPath(requested).name
    matches = [
        name for name in candidates if PurePosixPath(_normalize_lora(name)).name == requested_base
    ]
    return matches[0] if len(matches) == 1 else None


# {
#   責務: [_normalize_lora: normalize path separators and model file extensions]
#   処理: [case-fold a relative adapter identifier for catalog comparison]
#   引数: [value: prompt reference or catalog path]
#   戻り値: [str: normalized name]
# }
def _normalize_lora(value: str) -> str:
    normalized = value.replace("\\", "/").strip().strip("/").casefold()
    path = PurePosixPath(normalized)
    if path.suffix in {".safetensors", ".ckpt", ".pt", ".pth", ".bin"}:
        return str(path.with_suffix(""))
    return normalized
