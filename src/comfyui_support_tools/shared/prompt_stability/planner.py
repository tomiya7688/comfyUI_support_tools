"""Preview-first prompt and candidate-budget adjustment planner."""

from __future__ import annotations

import re
from collections.abc import Callable

from .contracts import (
    ApplyMode,
    ComputeBudget,
    PromptAdjustmentResult,
    PromptRiskReport,
    PromptRiskRequest,
    RiskLevel,
    RiskTolerance,
)
from .policy import StabilityPolicyRegistry

PromptRewriter = Callable[[str, PromptRiskReport, str], str]
ConfigAdjuster = Callable[[dict[str, object], PromptRiskReport, str], dict[str, object]]


# {
# 責務: [PromptAdjustmentPlanner: suggestion/auto apply previewを計画する]
# フィールド: [policy registry, optional model-aware rewrite hooks]
# 処理: [intent lockを守り予算内の候補数・prompt・configを構成する]
# }
class PromptAdjustmentPlanner:
    # {
    # 責務: [__init__: policyとmodel-aware adjustment adapterを設定する]
    # 処理: [1: registryとcallable hookを保持する]
    # 引数: [self: planner, policies: policy registry, rewriter: prompt adapter, config_adjuster: backend config adapter]
    # 戻り値: []
    # }
    def __init__(
        self,
        policies: StabilityPolicyRegistry | None = None,
        *,
        rewriter: PromptRewriter | None = None,
        config_adjuster: ConfigAdjuster | None = None,
    ) -> None:
        self.policies = policies or StabilityPolicyRegistry()
        self.rewriter = rewriter
        self.config_adjuster = config_adjuster

    # {
    # 責務: [plan: riskに対応するpreview可能なadjustmentを構築する]
    # 処理: [1: candidate budgetを解決する, 2: opted-in prompt/config/negative adjustmentを適用する]
    # 引数: [self: planner, request: original generation request, report: risk analysis]
    # 戻り値: [PromptAdjustmentResult: before/afterとoverrideable plan]
    # }
    def plan(self, request: PromptRiskRequest, report: PromptRiskReport) -> PromptAdjustmentResult:
        settings = request.settings
        profile = self.policies.resolve(request)
        mode_enabled = settings.enabled and (
            (request.content_mode.value == "sfw" and settings.apply_to_sfw)
            or (request.content_mode.value == "nsfw" and settings.apply_to_nsfw)
        )
        original_count = _candidate_count(request.parameters)
        candidate_count = original_count
        locked_candidate_count = settings.locked_values.get("candidate_count")
        if (
            isinstance(locked_candidate_count, int)
            and not isinstance(locked_candidate_count, bool)
            and 1 <= locked_candidate_count <= 16
        ):
            candidate_count = locked_candidate_count
        if (
            mode_enabled
            and settings.apply_mode != ApplyMode.SUGGEST_ONLY
            and (settings.expand_candidates or settings.forced_candidate_count is not None)
            and "candidate_count" not in settings.disabled_adjustments
            and locked_candidate_count is None
        ):
            candidate_count = settings.forced_candidate_count or _candidate_budget(
                report.overall_risk, settings.budget, settings.risk_tolerance
            )
        prompt = request.prompt
        negative = request.negative_prompt
        params = dict(request.parameters)
        logs: list[str] = []
        applied = mode_enabled and settings.apply_mode != ApplyMode.SUGGEST_ONLY
        if (
            applied
            and not settings.force_original_prompt
            and settings.adjust_prompt
            and "prompt" not in settings.disabled_adjustments
        ):
            if self.rewriter is not None:
                prompt = self.rewriter(prompt, report, request.model_family)
                if prompt != request.prompt:
                    logs.append("Applied model-family prompt rewrite; review it before generation.")
            elif settings.intent_preservation.value != "strict":
                prompt = _dedupe_exact_phrases(prompt)
                if prompt != request.prompt:
                    logs.append("Removed repeated exact prompt clauses.")
        if (
            applied
            and request.negative_supported
            and "negative" not in settings.disabled_adjustments
        ):
            additions = tuple(
                term
                for term in profile.negative_terms
                if term.casefold() not in negative.casefold()
            )
            if additions:
                negative = ", ".join(part for part in (negative.strip(), *additions) if part)
                logs.append(f"Added {len(additions)} profile negative-prompt terms.")
        if applied and settings.adjust_generation_config and self.config_adjuster is not None:
            adjusted = self.config_adjuster(params, report, request.model_family)
            locks = dict(settings.locked_values)
            params = {**adjusted, **locks}
            if params != dict(request.parameters):
                logs.append("Applied model/backend config policy while honoring locked values.")
        elif (
            applied
            and settings.adjust_generation_config
            and "config" not in settings.disabled_adjustments
        ):
            if (
                "config" not in settings.disabled_adjustments
                and "steps" not in settings.locked_values
                and report.overall_risk in (RiskLevel.HIGH, RiskLevel.EXTREME)
            ):
                steps = params.get("steps")
                if isinstance(steps, int) and not isinstance(steps, bool):
                    params["steps"] = min(steps + 4, 60)
                    logs.append("Raised steps modestly under the built-in high-risk policy.")
        if applied:
            params.update(settings.locked_values)
        if applied and candidate_count != original_count:
            logs.append(
                f"Expanded candidates from {original_count} to {candidate_count} within the selected budget."
            )
        retry_limit = (
            min(3, max(0, candidate_count - 1))
            if applied
            and settings.apply_mode == ApplyMode.AUTO_EVALUATE_RETRY
            and settings.retry_or_repair
            and settings.budget in (ComputeBudget.QUALITY, ComputeBudget.OVERNIGHT)
            else 0
        )
        backend_hint = profile.preferred_backend or None
        return PromptAdjustmentResult(
            original_prompt=request.prompt,
            adjusted_prompt=prompt,
            original_negative_prompt=request.negative_prompt,
            adjusted_negative_prompt=negative,
            original_parameters=dict(request.parameters),
            adjusted_parameters=params,
            original_candidate_count=original_count,
            candidate_count=candidate_count,
            backend_hint=backend_hint,
            adjustment_log=tuple(logs),
            requires_preview=settings.show_preview,
            applied=applied,
            retry_limit=retry_limit,
            report=report,
        )


# {
# 責務: [_candidate_count: generation parametersから安全な候補数を読む]
# 処理: [candidate_count/count/nの順で整数値を解決する]
# 引数: [parameters: generation config]
# 戻り値: [count: 1..16に制限した候補数]
# }
def _candidate_count(parameters: dict[str, object]) -> int:
    for key in ("candidate_count", "count", "n"):
        value = parameters.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return min(16, max(1, value))
    return 1


# {
# 責務: [_candidate_budget: riskとcompute budgetから候補数上限を決める]
# 処理: [risk bucketとbudget上限の小さい方を返す]
# 引数: [risk: overall risk, budget: compute budget]
# 戻り値: [count: bounded candidate count]
# }
def _candidate_budget(risk: RiskLevel, budget: ComputeBudget, tolerance: RiskTolerance) -> int:
    if risk in (RiskLevel.LOW, RiskLevel.MEDIUM):
        return 1 if budget is ComputeBudget.FAST else 2
    limits = {
        ComputeBudget.FAST: 2,
        ComputeBudget.STANDARD: 4,
        ComputeBudget.QUALITY: 8,
        ComputeBudget.OVERNIGHT: 16,
    }
    count = limits[budget]
    if tolerance is RiskTolerance.CONSERVATIVE:
        return max(1, count // 2)
    if tolerance is RiskTolerance.AGGRESSIVE:
        return min(16, count * 2)
    return count


# {
# 責務: [_dedupe_exact_phrases: 同一句だけを意図を変えずに除去する]
# 処理: [comma/semicolon句をcase-insensitiveで一度だけ残す]
# 引数: [prompt: original user prompt]
# 戻り値: [prompt: 重複除去後prompt]
# }
def _dedupe_exact_phrases(prompt: str) -> str:
    pieces = re.split(r"([,;])", prompt)
    kept: list[str] = []
    seen: set[str] = set()
    for index in range(0, len(pieces), 2):
        phrase = pieces[index]
        key = " ".join(phrase.casefold().split())
        if key and key not in seen:
            seen.add(key)
            kept.append(phrase.strip())
        if index + 1 < len(pieces) and kept:
            kept.append(pieces[index + 1])
    return " ".join(kept).strip(" ,;")
