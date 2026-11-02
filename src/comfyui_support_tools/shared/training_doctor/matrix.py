"""Fixed personalization prompt matrices for fair checkpoint evaluation."""

from __future__ import annotations

from .contracts import FixedConditions, PromptScenario, ValidationPlan, ValidationTask


# {
# 責務: [_label: resolve a concept label with a safe display fallback]
# 処理: [trim user labels and substitute a stable default for empty values]
# 引数: [labels: supplied concept names, index: concept position, fallback: default label]
# 戻り値: [str: nonempty display concept]
# }
def _label(labels: tuple[str, ...], index: int, fallback: str) -> str:
    return labels[index].strip() if index < len(labels) and labels[index].strip() else fallback


# {
# 責務: [_scenario: construct a fixed prompt scenario]
# 処理: [store prompt semantics and whether the trained trigger is expected]
# 引数: [key: stable case identity, prompt: fixed prompt text, trigger_present: trigger policy, concepts: expected concept labels]
# 戻り値: [PromptScenario: immutable matrix row]
# }
def _scenario(key: str, prompt: str, trigger_present: bool, *concepts: str) -> PromptScenario:
    return PromptScenario(key, prompt, trigger_present, tuple(concepts))


# {
# 責務: [fixed_validation_plan: create a deterministic task-specific prompt matrix]
# 処理: [choose coverage prompts, inject concept names, and bind shared render conditions]
# 引数: [task: character/style/object/multi-concept task, trigger: learned token, concepts: optional named concepts, conditions: fixed generation settings]
# 戻り値: [ValidationPlan: reproducible validation matrix]
# エラー: [ValueError: multi-concept task requires two distinct concepts]
# }
def fixed_validation_plan(
    task: ValidationTask,
    trigger: str = "<trigger>",
    concepts: tuple[str, ...] = (),
    conditions: FixedConditions | None = None,
    trigger_candidates: tuple[str, ...] = (),
    recommended_tags: tuple[str, ...] = (),
) -> ValidationPlan:
    first, second = _label(concepts, 0, "concept A"), _label(concepts, 1, "concept B")
    if task is ValidationTask.MULTI_CONCEPT and first.casefold() == second.casefold():
        raise ValueError("multi-concept validation requires two distinct concept labels")
    tag_prompt = f"{trigger}, {', '.join(recommended_tags)}" if recommended_tags else ""
    matrices = {
        ValidationTask.CHARACTER: (
            _scenario("trigger_only", f"portrait of {trigger}", True, first),
            _scenario("different_pose", f"{trigger}, dynamic full-body pose", True, first),
            _scenario("different_clothing", f"{trigger}, wearing a formal coat", True, first),
            _scenario("different_background", f"{trigger}, on a beach at noon", True, first),
            _scenario("different_lighting", f"{trigger}, dramatic blue-hour lighting", True, first),
            _scenario("different_style", f"{trigger}, watercolor illustration", True, first),
            *((_scenario("trigger_with_tags", tag_prompt, True, first),) if tag_prompt else ()),
            _scenario("trigger_absent", "a person in a red coat, no named character", False),
        ),
        ValidationTask.STYLE: (
            _scenario("portrait", f"{trigger}, portrait of an adult", True, first),
            _scenario("object", f"{trigger}, ceramic vase on a table", True, first),
            _scenario("landscape", f"{trigger}, mountain lake at sunrise", True, first),
            _scenario(
                "simple_composition", f"{trigger}, one object on a plain background", True, first
            ),
            _scenario("complex_composition", f"{trigger}, detailed busy city street", True, first),
            *((_scenario("trigger_with_tags", tag_prompt, True, first),) if tag_prompt else ()),
            _scenario("trigger_absent", "a studio photograph of a fruit bowl", False),
        ),
        ValidationTask.OBJECT: (
            _scenario("front_view", f"{trigger}, front view", True, first),
            _scenario("side_view", f"{trigger}, side view", True, first),
            _scenario("back_view", f"{trigger}, back view", True, first),
            _scenario("different_scale", f"small {trigger} beside a large chair", True, first),
            *((_scenario("trigger_with_tags", tag_prompt, True, first),) if tag_prompt else ()),
            _scenario("trigger_absent", "a wooden chair in an empty room", False),
        ),
        ValidationTask.MULTI_CONCEPT: (
            _scenario("a_only", f"{trigger} {first}, alone", True, first),
            _scenario("b_only", f"{trigger} {second}, alone", True, second),
            _scenario("a_plus_b", f"{trigger} {first} together with {second}", True, first, second),
            *(
                (
                    _scenario(
                        "trigger_with_tags",
                        f"{tag_prompt} {first} and {second}",
                        True,
                        first,
                        second,
                    ),
                )
                if tag_prompt
                else ()
            ),
            _scenario("neither", "a quiet garden with a stone path", False),
        ),
    }
    variants = trigger_candidates or (trigger,)
    if len(variants) > 8 or any(not candidate.strip() for candidate in variants):
        raise ValueError("trigger candidates must contain 1..8 nonempty values")
    scenarios = []
    for scenario in matrices[task]:
        if not scenario.trigger_present:
            scenarios.append(scenario)
            continue
        for index, candidate in enumerate(variants):
            scenarios.append(
                PromptScenario(
                    f"{scenario.key}_trigger_{index + 1}",
                    scenario.prompt.replace(trigger, candidate),
                    True,
                    scenario.concept_labels,
                    candidate,
                )
            )
    return ValidationPlan(
        task,
        tuple(scenarios),
        conditions or FixedConditions(),
        trigger,
        recommended_tags,
        variants,
    )
