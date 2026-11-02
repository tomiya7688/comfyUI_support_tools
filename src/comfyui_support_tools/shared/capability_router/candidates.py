"""Cross-family Best-of-N generation planning and task-specific ranking."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .contracts import CapabilityRoute, GenerationCapability


# {
#   責務: [CapabilityCandidate: family capabilityによる生成結果とtask別評価値を保持する]
#   フィールド: [model, capability, image_bytes, metric_breakdown, selection_metric]
# }
@dataclass(frozen=True, slots=True)
class CapabilityCandidate:
    model: str
    capability: GenerationCapability
    image_bytes: bytes
    metric_breakdown: Mapping[str, float]
    selection_metric: str


# {
#   責務: [CrossFamilyCandidatePlan: 同じpromptのfamilyごとのdraftをtask metricで選んだ結果]
#   フィールド: [candidates, selection_metric, reason]
# }
@dataclass(frozen=True, slots=True)
class CrossFamilyCandidatePlan:
    candidates: tuple[CapabilityCandidate, ...]
    selection_metric: str
    reason: str


# {
#   責務: [run_cross_family_best_of_n: route候補modelごとに同じpromptを生成しuse-case evaluatorで順位付けする]
#   処理: [explicit task-specific metricでsortし, evaluatorの全dimension breakdownを候補へ保持する]
#   引数: [route: distinct-family alternatives, prompt: shared prompt, generate: modelごとのbackend callback, evaluate: task-specific scorer, selection_metric: evaluatorのnamed metric, top_k: return候補数]
#   戻り値: [CrossFamilyCandidatePlan: task metricで並べたcandidate images]
#   エラー: [LookupError: selection metricがevaluatorにない, ValueError: invalid result/count]
# }
def run_cross_family_best_of_n(
    route: CapabilityRoute,
    prompt: str,
    generate: Callable[[str, GenerationCapability], bytes],
    evaluate: Callable[[str, bytes, str], Mapping[str, float]],
    *,
    selection_metric: str,
    top_k: int,
) -> CrossFamilyCandidatePlan:
    if (
        not selection_metric.strip()
        or isinstance(top_k, bool)
        or not isinstance(top_k, int)
        or not 1 <= top_k <= len(route.candidates)
    ):
        raise ValueError("selection metric and top_k must be valid for the routed candidate count")
    candidates = []
    for model, capability in route.candidates:
        image_bytes = generate(model, capability)
        if not image_bytes:
            raise ValueError(f"candidate generation returned no image bytes for {model}")
        breakdown = dict(evaluate(prompt, image_bytes, capability.profile_id))
        if selection_metric not in breakdown:
            raise LookupError(f"evaluator did not return the requested metric: {selection_metric}")
        if any(
            isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 1
            for score in breakdown.values()
        ):
            raise ValueError(
                "candidate evaluator scores must be finite values between zero and one"
            )
        candidates.append(
            CapabilityCandidate(model, capability, image_bytes, breakdown, selection_metric)
        )
    ranked = tuple(
        sorted(
            candidates,
            key=lambda item: (-item.metric_breakdown[selection_metric], item.capability.profile_id),
        )[:top_k]
    )
    return CrossFamilyCandidatePlan(
        ranked,
        selection_metric,
        f"Ranked {len(candidates)} model families by task-specific metric {selection_metric!r}; other score dimensions remain available.",
    )
