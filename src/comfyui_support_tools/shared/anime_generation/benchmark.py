"""Prepare fair, model-policy-aware anime benchmark prompts."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    AnimeContentMode,
    AnimeIntent,
    AnimeModelProfile,
)
from .policy import apply_anime_prompt_policy


# {
#   責務: [AnimeBenchmarkCase: define a reusable evaluation prompt and intent]
#   フィールド: [case_id, prompt, negative prompt, intent, content mode]
#   処理: [compare model outputs after each family's own prompt policy is applied]
# }
@dataclass(frozen=True)
class AnimeBenchmarkCase:
    case_id: str
    prompt: str
    negative_prompt: str = ""
    intent: AnimeIntent = AnimeIntent.GENERAL
    content_mode: AnimeContentMode = AnimeContentMode.UNSPECIFIED

    # {
    #   責務: [__post_init__: validate a model-neutral benchmark case]
    #   処理: [require a stable identifier, prompt text, and typed use-case controls]
    #   引数: [self: benchmark case]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.case_id.strip() or not self.prompt.strip():
            raise ValueError("benchmark case requires an ID and prompt")
        if not isinstance(self.intent, AnimeIntent) or not isinstance(
            self.content_mode, AnimeContentMode
        ):
            raise ValueError("benchmark controls must use declared enums")


# {
#   責務: [AnimeBenchmarkPrompt: hold one profile-specific rendered benchmark input]
#   フィールド: [case_id, profile_id, positive prompt, negative prompt, intent]
#   処理: [record the actual policy text used for later quality review]
# }
@dataclass(frozen=True)
class AnimeBenchmarkPrompt:
    case_id: str
    profile_id: str
    prompt: str
    negative_prompt: str
    intent: AnimeIntent


# {
#   責務: [build_benchmark_prompts: render the same cases for one model family]
#   処理: [apply the selected family's policy independently to each benchmark case]
#   引数: [profile: model profile, cases: common evaluation cases]
#   戻り値: [tuple[AnimeBenchmarkPrompt, ...]: rendered prompt artifacts]
# }
def build_benchmark_prompts(
    profile: AnimeModelProfile, cases: tuple[AnimeBenchmarkCase, ...]
) -> tuple[AnimeBenchmarkPrompt, ...]:
    if any(not isinstance(case, AnimeBenchmarkCase) for case in cases):
        raise TypeError("cases must contain AnimeBenchmarkCase values")
    rendered = []
    seen_ids: set[str] = set()
    for case in cases:
        if case.case_id in seen_ids:
            raise ValueError(f"duplicate benchmark case ID: {case.case_id}")
        seen_ids.add(case.case_id)
        prompt, negative = apply_anime_prompt_policy(
            profile,
            case.prompt,
            case.negative_prompt,
            intent=case.intent,
            content_mode=case.content_mode,
        )
        rendered.append(
            AnimeBenchmarkPrompt(
                case.case_id,
                profile.profile_id,
                prompt,
                negative,
                case.intent,
            )
        )
    return tuple(rendered)
