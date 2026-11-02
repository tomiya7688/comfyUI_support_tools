"""Deterministic, extensible prompt-risk analysis; this is not moderation."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .contracts import (
    PromptRiskReport,
    PromptRiskRequest,
    RiskFactor,
    RiskLevel,
)
from .policy import StabilityPolicyRegistry

_CONTRADICTIONS = (
    ("close-up", "full body"),
    ("portrait", "wide shot"),
    ("daylight", "night"),
    ("standing", "lying"),
    ("front view", "back view"),
    ("single person", "group"),
)
_COMPLEX_INTERACTION = ("holding", "embracing", "touching", "interacting", "fighting", "grabbing")


# {
# 責務: [PromptRiskAnalyzer: prompt/mode/model特徴からriskを推定する]
# フィールド: [policy registry]
# 処理: [構造riskと拡張可能なprofile ruleを集約する]
# }
class PromptRiskAnalyzer:
    # {
    # 責務: [__init__: prompt risk policy registryを設定する]
    # 処理: [registryが省略された場合はdefault profilesを使う]
    # 引数: [self: analyzer, policies: profile registry]
    # 戻り値: []
    # }
    def __init__(self, policies: StabilityPolicyRegistry | None = None) -> None:
        self.policies = policies or StabilityPolicyRegistry()

    # {
    # 責務: [analyze: risk factorsを解析しreportを構築する]
    # 処理: [1: baseline structural rulesを評価する, 2: profile/override ruleを集約する]
    # 引数: [self: analyzer, request: generation prompt request]
    # 戻り値: [PromptRiskReport: riskとprovenance]
    # }
    def analyze(self, request: PromptRiskRequest) -> PromptRiskReport:
        settings = request.settings
        profile = self.policies.resolve(request)
        if (
            not settings.enabled
            or (request.content_mode.value == "sfw" and not settings.apply_to_sfw)
            or (request.content_mode.value == "nsfw" and not settings.apply_to_nsfw)
        ):
            return PromptRiskReport(
                request.content_mode,
                RiskLevel.LOW,
                (),
                (),
                (),
                (),
                (),
                (),
                1.0,
                {
                    "guard_enabled": False,
                    "backend": request.backend,
                    "model_family": request.model_family,
                },
            )
        factors = list(_structural_rules(request))
        family = request.model_family.casefold()
        if family and any(family == item.casefold() for item in profile.incompatible_families):
            factors.append(
                RiskFactor(
                    "backend.family_incompatible",
                    RiskLevel.HIGH,
                    f"The selected stability profile has no compatible policy for model family {request.model_family}",
                    0.9,
                )
            )
        for rule in profile.rules:
            factors.extend(rule(request))
        factors = [factor for factor in factors if factor.key not in settings.ignored_risk_factors]
        unique = {factor.key: factor for factor in factors}
        factors = list(unique.values())
        level = _aggregate_risk(factors)
        conflicts = tuple(
            factor.description for factor in factors if factor.key.startswith("conflict.")
        )
        lora_conflicts = tuple(
            factor.description for factor in factors if factor.key.startswith("lora.")
        )
        backend_risks = tuple(
            factor.description for factor in factors if factor.key.startswith("backend.")
        )
        suggestions = tuple(
            _suggestion(factor.key) for factor in factors if _suggestion(factor.key)
        )
        confidence = sum(factor.confidence for factor in factors) / len(factors) if factors else 0.9
        return PromptRiskReport(
            content_mode=request.content_mode,
            overall_risk=level,
            risk_factors=tuple(factors),
            affected_entities=tuple(
                dict.fromkeys(entity for factor in factors for entity in factor.entities)
            ),
            conflicting_constraints=conflicts,
            lora_conflicts=lora_conflicts,
            backend_compatibility_risks=backend_risks,
            suggested_adjustments=suggestions,
            confidence=confidence,
            provenance={
                "guard_enabled": True,
                "backend": request.backend,
                "model": request.model,
                "model_family": request.model_family,
                "task": request.task,
                "profile_mode": profile.content_mode.value,
                "rule_keys": tuple(unique),
            },
        )


# {
# 責務: [_structural_rules: 汎用prompt構造riskを算出する]
# 処理: [1: constraint density/conflict/LoRAを検出する, 2: risk factorsを返す]
# 引数: [request: prompt risk request]
# 戻り値: [RiskFactor iterable: 検出risk]
# }
def _structural_rules(request: PromptRiskRequest) -> Iterable[RiskFactor]:
    prompt = request.prompt.casefold()
    yield from _constraint_rules(request, prompt)
    yield from _scene_rules(request, prompt)
    yield from _lora_rules(request)
    yield from _context_rules(request, prompt)


# {
# 責務: [_constraint_rules: flat/structured condition densityと矛盾を検出する]
# 処理: [1: constraint volumeを判定する, 2: structured/text contradictionsを返す]
# 引数: [request: risk request, prompt: casefold済みprompt]
# 戻り値: [RiskFactor iterable: complexity and conflict rules]
# }
def _constraint_rules(request: PromptRiskRequest, prompt: str) -> Iterable[RiskFactor]:
    words = re.findall(r"[\w'-]+", prompt)
    constraint_count = (
        sum(prompt.count(token) for token in (",", ";", " and ", " with ", " plus ")) + 1
    )
    if constraint_count >= 14 or len(words) >= 100:
        yield RiskFactor(
            "constraints.dense", RiskLevel.HIGH, "Many simultaneous prompt constraints", 0.8
        )
    elif constraint_count >= 8 or len(words) >= 55:
        yield RiskFactor(
            "constraints.many",
            RiskLevel.MEDIUM,
            "Prompt contains many simultaneous constraints",
            0.72,
        )
    structured_count = sum(len(values) for values in request.structured_prompt.values())
    if structured_count >= 18:
        yield RiskFactor(
            "structure.dense",
            RiskLevel.HIGH,
            "Structured prompt contains many simultaneous subject, pose, and scene constraints",
            0.86,
        )
    elif structured_count >= 10:
        yield RiskFactor(
            "structure.many",
            RiskLevel.MEDIUM,
            "Structured prompt spans many simultaneous constraints",
            0.78,
        )
    structured_terms = {
        value.casefold()
        for category, values in request.structured_prompt.items()
        if category.casefold() in {"composition", "pose", "camera", "framing"}
        for value in values
    }
    for first, second in _CONTRADICTIONS:
        if first in structured_terms and second in structured_terms:
            yield RiskFactor(
                f"conflict.structured.{first}.{second}",
                RiskLevel.HIGH,
                f"Structured composition fields conflict: {first} / {second}",
                0.98,
                (first, second),
            )
    for first, second in _CONTRADICTIONS:
        if first in prompt and second in prompt:
            yield RiskFactor(
                f"conflict.{first}.{second}",
                RiskLevel.HIGH,
                f"Conflicting composition constraints: {first} / {second}",
                0.95,
                (first, second),
            )


# {
# 責務: [_scene_rules: entity/pose/detail密度の構図riskを検出する]
# 処理: [1: 多人数sceneを検出する, 2: body/face/hand/background負荷を評価する]
# 引数: [request: risk request, prompt: casefold済みprompt]
# 戻り値: [RiskFactor iterable: scene risk]
# }
def _scene_rules(request: PromptRiskRequest, prompt: str) -> Iterable[RiskFactor]:
    tags = set(
        re.findall(
            r"\b(?:\d+\s*girls?|\d+\s*boys?|\d+\s*people|group|crowd|multiple characters)\b", prompt
        )
    )
    if tags:
        yield RiskFactor(
            "entities.multiple",
            RiskLevel.MEDIUM,
            "Multiple-character composition raises identity and interaction complexity",
            0.75,
            tuple(sorted(tags)),
        )
    body_detail = any(term in prompt for term in ("full body", "full-body", "fullbody"))
    hand_detail = any(
        term in prompt for term in ("detailed hands", "hand interaction", "holding", "fingers")
    )
    face_detail = any(
        term in prompt for term in ("detailed face", "facial detail", "detailed eyes")
    )
    background_detail = any(
        term in prompt
        for term in ("complex background", "highly detailed background", "crowded background")
    )
    if sum((body_detail, hand_detail, face_detail, background_detail)) >= 3:
        yield RiskFactor(
            "composition.detail_overload",
            RiskLevel.HIGH,
            "Full-body, face/hand detail, and background complexity compete for attention",
            0.82,
            ("face", "hands", "body", "background"),
        )
    if sum(term in prompt for term in _COMPLEX_INTERACTION) >= 2:
        yield RiskFactor(
            "pose.interaction",
            RiskLevel.HIGH,
            "Several complex pose or contact instructions are combined",
            0.76,
            ("pose", "contact"),
        )


# {
# 責務: [_lora_rules: LoRA数量・役割・強度の競合を検出する]
# 処理: [1: style/pose strengthを比較する, 2: unknown-roleと過多なLoRAを報告する]
# 引数: [request: risk request]
# 戻り値: [RiskFactor iterable: LoRA conflicts]
# }
def _lora_rules(request: PromptRiskRequest) -> Iterable[RiskFactor]:
    roles = {role.casefold(): weight for _, weight, role in request.loras if role}
    if {"style", "pose"}.issubset(roles) and min(roles["style"], roles["pose"]) >= 0.8:
        yield RiskFactor(
            "lora.style_pose",
            RiskLevel.HIGH,
            "Strong style and pose LoRAs may compete for rendering and structure",
            0.8,
        )
    if any(weight > 1.2 or weight < 0 for _, weight, _ in request.loras):
        yield RiskFactor(
            "lora.strength",
            RiskLevel.MEDIUM,
            "One or more LoRA strengths are outside the usual 0.0–1.2 range",
            0.7,
        )
    lora_count = len(request.loras)
    if lora_count >= 4:
        yield RiskFactor(
            "lora.count",
            RiskLevel.HIGH,
            f"{lora_count} LoRAs may compete for style, identity, or pose",
            0.78,
            tuple(item[0] for item in request.loras),
        )
    elif lora_count >= 2:
        families = {item[2].casefold() for item in request.loras if item[2]}
        if len(families) < lora_count:
            yield RiskFactor(
                "lora.overlap",
                RiskLevel.MEDIUM,
                "Multiple LoRAs have unknown or overlapping roles",
                0.65,
                tuple(item[0] for item in request.loras),
            )


# {
# 責務: [_context_rules: backend syntax/content mode/historyに依存するriskを検出する]
# 処理: [1: model family prompt syntaxを確認する, 2: SFW/NSFW/history factorを返す]
# 引数: [request: risk request, prompt: casefold済みprompt]
# 戻り値: [RiskFactor iterable: contextual risk]
# }
def _context_rules(request: PromptRiskRequest, prompt: str) -> Iterable[RiskFactor]:
    body_detail = any(term in prompt for term in ("full body", "full-body", "fullbody"))
    hand_detail = any(
        term in prompt for term in ("detailed hands", "hand interaction", "holding", "fingers")
    )
    background_detail = any(
        term in prompt
        for term in ("complex background", "highly detailed background", "crowded background")
    )
    if re.search(r"\([^()]{1,80}:\d+(?:\.\d+)?\).{0,100}\([^()]{1,80}:\d+(?:\.\d+)?\)", prompt):
        yield RiskFactor(
            "weights.nested",
            RiskLevel.MEDIUM,
            "Multiple weighted prompt fragments may overemphasize local conditions",
            0.65,
        )
    family = request.model_family.casefold()
    if (
        family
        and any(token in prompt for token in ("BREAK", "<lora:", "[::"))
        and any(family_token in family for family_token in ("qwen", "flux"))
    ):
        yield RiskFactor(
            "backend.prompt_syntax",
            RiskLevel.MEDIUM,
            "Prompt contains weighted/tag syntax that may not map cleanly to the selected model family",
            0.74,
            (request.model_family,),
        )
    if (
        request.content_mode.value == "nsfw"
        and sum(
            term in prompt
            for term in ("multiple partners", "body interaction", "contact pose", "intertwined")
        )
        >= 2
    ):
        yield RiskFactor(
            "nsfw.interaction",
            RiskLevel.HIGH,
            "Complex NSFW body interaction requires pose/contact consistency evaluation",
            0.75,
            ("anatomy", "contact"),
        )
    if request.content_mode.value == "sfw" and body_detail and hand_detail and background_detail:
        yield RiskFactor(
            "sfw.full_scene_detail",
            RiskLevel.HIGH,
            "SFW full-body hand detail and dense background increase structural failure risk",
            0.8,
            ("body", "hands", "background"),
        )
    if request.prior_failures:
        failures = tuple(dict.fromkeys(request.prior_failures[:8]))
        yield RiskFactor(
            "history.prior_failures",
            RiskLevel.HIGH,
            "The selected model/backend has recent related generation failures",
            0.68,
            failures,
        )
    return


# {
# 責務: [_aggregate_risk: rule severityをoverall riskへまとめる]
# 処理: [最も高いseverityを返しrisk factor不在時はlowを返す]
# 引数: [factors: risk factors]
# 戻り値: [RiskLevel: 集約risk]
# }
def _aggregate_risk(factors: list[RiskFactor]) -> RiskLevel:
    order = (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.EXTREME)
    return max((factor.severity for factor in factors), key=order.index, default=RiskLevel.LOW)


# {
# 責務: [_suggestion: risk keyを分かりやすいadjustmentへ変換する]
# 処理: [risk familyに応じた提案文を返す]
# 引数: [key: risk factor key]
# 戻り値: [suggestion: adjustment description]
# }
def _suggestion(key: str) -> str:
    return {
        "constraints.dense": "Reduce low-priority details while preserving the subject, pose, and composition.",
        "constraints.many": "Merge duplicate modifiers and group details by subject, pose, and scene.",
        "composition.detail_overload": "Prioritize either full-body composition or dense facial/hand detail.",
        "composition.conflict": "Resolve contradictory framing or pose instructions before generation.",
        "pose.interaction": "Use a pose/contact evaluator and increase candidates within the selected budget.",
        "lora.count": "Review LoRA roles and reduce conflicting strengths using the LoRA quality policy.",
        "lora.overlap": "Assign distinct character/style/pose roles and lock user-approved weights.",
        "weights.nested": "Flatten or reduce stacked emphasis according to the selected model family syntax.",
        "nsfw.interaction": "Evaluate anatomy and contact consistency with the NSFW quality profile.",
        "sfw.full_scene_detail": "Use the SFW face/hand/composition evaluators and expand candidates moderately.",
    }.get(
        key.split(".")[0] + "." + key.split(".")[1] if "." in key else key,
        "Review model-family compatibility and user-locked constraints.",
    )
