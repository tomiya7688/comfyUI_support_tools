"""Resolve registered identity and outfit traits into prompt-ready content."""

from comfyui_support_tools.shared.contracts.character_registry import (
    CharacterProfile,
    CharacterPromptResolution,
    CharacterTrait,
    OutfitProfile,
    VisibilityContext,
    VisibilityDecision,
    validate_character_profile,
)

INJECTION_SIGNALS = frozenset(
    {"high_camera", "sitting", "crouching", "lying", "wind", "sheer", "wet", "backlight"}
)


# {
#   責務: [resolve_visibility: evidenceが十分なhidden traitだけをpromptへ出す]
#   処理: [1: explicit requestを最優先する 2: visibility/transparency signalsを集計する 3: uncertainはomitする]
#   引数: [trait: hidden attribute, context: pose/camera/material evidence, quality_mode: resolution level]
#   戻り値: [VisibilityDecision: explainable conservative decision]
# }
def resolve_visibility(
    trait: CharacterTrait,
    context: VisibilityContext,
    *,
    quality_mode: str = "standard",
) -> VisibilityDecision:
    if quality_mode not in {"standard", "quality"}:
        raise ValueError("quality_mode must be standard or quality")
    signals = set(context.pose_signals + context.camera_signals + context.material_signals)
    signals.update(context.scene_signals)
    reasons = [f"evidence:{signal}" for signal in sorted(signals & INJECTION_SIGNALS)]
    if trait.value.casefold() in {item.casefold() for item in context.explicit_attribute_requests}:
        return VisibilityDecision(trait.value, 1.0, 0.0, 1.0, ("explicit_user_request",), "inject")

    visibility_evidence = sum(
        signal in signals for signal in ("high_camera", "sitting", "crouching", "lying", "wind")
    )
    transparency_evidence = sum(signal in signals for signal in ("sheer", "wet", "backlight"))
    if trait.visibility_conditions:
        required = set(trait.visibility_conditions)
        matched = required & signals
        reasons.extend(f"required:{item}" for item in sorted(matched))
        if not required.issubset(signals):
            return VisibilityDecision(
                trait.value, 0.0, 0.0, 0.0, tuple(reasons or ("required_signals_missing",)), "omit"
            )
        visibility_evidence += len(required)
    visible = min(1.0, visibility_evidence * 0.3)
    transparent = min(1.0, transparency_evidence * 0.4)
    confidence = min(1.0, max(visible, transparent))
    should_inject = visible >= 0.6 or transparent >= 0.6
    if quality_mode == "quality":
        should_inject = visible >= 0.3 or transparent >= 0.4
    if not reasons:
        reasons.append("no_visibility_evidence")
    return VisibilityDecision(
        trait.value,
        visible,
        transparent,
        confidence,
        tuple(reasons),
        "inject" if should_inject else "omit",
    )


# {
#   責務: [resolve_character_prompt: core/outfit/custom prompt ownershipを解決する]
#   処理: [1: profile/outfitを検証する 2: custom categoryでregistered outfitを抑制する 3: visible hidden traitsだけ加える]
#   引数: [profile/outfit_id/custom_traits/context/lora_active/model_traits/quality_mode]
#   戻り値: [CharacterPromptResolution: stable identityとexplainable resolved traits]
# }
def resolve_character_prompt(
    profile: CharacterProfile,
    *,
    outfit_id: str | None = None,
    custom_traits: tuple[CharacterTrait, ...] = (),
    context: VisibilityContext | None = None,
    lora_active: bool = False,
    model_equivalent_traits: frozenset[str] = frozenset(),
    quality_mode: str = "standard",
) -> CharacterPromptResolution:
    validate_character_profile(profile)
    selected_id = outfit_id or profile.default_outfit_id
    outfit = _find_outfit(profile, selected_id)
    custom_categories = {item.category for item in custom_traits}
    included = list(profile.core_traits)
    suppressed = []
    if outfit is not None:
        for trait in outfit.traits:
            if trait.category in custom_categories:
                if trait.category not in suppressed:
                    suppressed.append(trait.category)
            else:
                included.append(trait)

    visible_context = context or VisibilityContext()
    hidden_decisions = []
    if outfit is not None:
        for hidden_trait in outfit.hidden_traits:
            decision = resolve_visibility(hidden_trait, visible_context, quality_mode=quality_mode)
            hidden_decisions.append(decision)
            if decision.action == "inject":
                included.append(hidden_trait)
    included.extend(custom_traits)

    resolved_traits = [profile.trigger_name or profile.display_name]
    for item in included:
        if lora_active and item.value.casefold() in {
            trait.casefold() for trait in model_equivalent_traits
        }:
            continue
        if profile.prompt_policy == "compact" and item.confidence < 0.75:
            continue
        if item.value not in resolved_traits:
            resolved_traits.append(item.value)
    warnings = []
    if selected_id and outfit is None:
        warnings.append("selected_outfit_unavailable")
        selected_id = None
    return CharacterPromptResolution(
        profile.character_id,
        selected_id,
        tuple(resolved_traits),
        tuple(hidden_decisions),
        tuple(suppressed),
        tuple(warnings),
    )


# {
#   責務: [_find_outfit: requested/default outfitをprofileから解決する]
#   処理: [1: noneならNoneを返す 2: ID一致時だけimmutable profileを返す]
#   引数: [profile: character asset, outfit_id: stable outfit identifier]
#   戻り値: [OutfitProfile | None]
# }
def _find_outfit(profile: CharacterProfile, outfit_id: str | None) -> OutfitProfile | None:
    if outfit_id is None:
        return None
    return next((item for item in profile.outfit_profiles if item.outfit_id == outfit_id), None)
