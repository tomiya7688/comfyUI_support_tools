"""Apply registered model-specific prompt tags without rewriting user text."""

from __future__ import annotations

from .contracts import (
    AnimeContentMode,
    AnimeIntent,
    AnimeModelProfile,
)


# {
#   責務: [apply_anime_prompt_policy: expand one prompt with its selected model profile]
#   処理: [1: validate user inputs, 2: apply optional intent/content tags, 3: deduplicate model-native tags]
#   引数: [profile: declared family profile, prompt: user prompt, negative_prompt: user exclusions, intent: target use case, content_mode: optional explicit content profile]
#   戻り値: [tuple[str, str]: positive and negative prompt]
# }
def apply_anime_prompt_policy(
    profile: AnimeModelProfile,
    prompt: str,
    negative_prompt: str = "",
    *,
    intent: AnimeIntent = AnimeIntent.GENERAL,
    content_mode: AnimeContentMode = AnimeContentMode.UNSPECIFIED,
) -> tuple[str, str]:
    if not isinstance(profile, AnimeModelProfile):
        raise TypeError("profile must be an AnimeModelProfile")
    if not isinstance(prompt, str) or not isinstance(negative_prompt, str):
        raise TypeError("prompt and negative_prompt must be strings")
    if not isinstance(intent, AnimeIntent) or not isinstance(content_mode, AnimeContentMode):
        raise TypeError("intent and content_mode must use their declared enums")
    policy = profile.prompt_policy
    additions = [*policy.quality_tags]
    additions.extend(policy.intent_tags.get(intent, ()))
    if content_mode is not AnimeContentMode.UNSPECIFIED:
        additions.extend(policy.content_tags.get(content_mode, ()))
    positive_tags = _merge_tags(additions, prompt, policy.quality_position)
    positive = ", ".join(positive_tags)
    negative = ", ".join(_merge_tags(policy.negative_tags, negative_prompt, "prefix"))
    return positive, negative


# {
#   責務: [_merge_tags: merge policy tags with a comma-delimited prompt]
#   処理: [preserve user order, add policy tags in descriptor order, and remove case-insensitive duplicates]
#   引数: [policy_tags: additions, prompt: user-authored tag text]
#   戻り値: [tuple[str, ...]: ordered unique tags]
# }
def _merge_tags(
    policy_tags: list[str] | tuple[str, ...], prompt: str, position: str
) -> tuple[str, ...]:
    existing = [part.strip() for part in prompt.split(",") if part.strip()]
    policy = list(dict.fromkeys(tag.strip() for tag in policy_tags if tag.strip()))
    policy_keys = {tag.casefold() for tag in policy}
    remaining_user_tags = [tag for tag in existing if tag.casefold() not in policy_keys]
    combined = (
        [*policy, *remaining_user_tags] if position == "prefix" else [*remaining_user_tags, *policy]
    )
    seen: set[str] = set()
    unique = []
    for tag in combined:
        key = tag.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(tag)
    return tuple(unique)
