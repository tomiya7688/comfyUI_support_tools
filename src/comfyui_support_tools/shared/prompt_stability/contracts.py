"""Typed inputs and outputs for opt-in prompt stability analysis."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum


# {
# 責務: [ContentMode: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
class ContentMode(str, Enum):
    SFW = "sfw"
    NSFW = "nsfw"


# {
# 責務: [RiskLevel: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


# {
# 責務: [ApplyMode: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
class ApplyMode(str, Enum):
    SUGGEST_ONLY = "suggest_only"
    AUTO_APPLY = "auto_apply"
    AUTO_EVALUATE_RETRY = "auto_evaluate_retry"


# {
# 責務: [IntentPreservation: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
class IntentPreservation(str, Enum):
    STRICT = "strict"
    NORMAL = "normal"
    FLEXIBLE = "flexible"


# {
# 責務: [RiskTolerance: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
class RiskTolerance(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


# {
# 責務: [ComputeBudget: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
class ComputeBudget(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    QUALITY = "quality"
    OVERNIGHT = "overnight"


# {
# 責務: [GuardSettings: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
@dataclass(frozen=True)
class GuardSettings:
    enabled: bool = False
    apply_to_sfw: bool = True
    apply_to_nsfw: bool = True
    apply_mode: ApplyMode = ApplyMode.SUGGEST_ONLY
    intent_preservation: IntentPreservation = IntentPreservation.STRICT
    risk_tolerance: RiskTolerance = RiskTolerance.BALANCED
    budget: ComputeBudget = ComputeBudget.STANDARD
    adjust_prompt: bool = True
    adjust_generation_config: bool = True
    expand_candidates: bool = True
    retry_or_repair: bool = True
    show_preview: bool = True
    force_original_prompt: bool = False
    disabled_adjustments: frozenset[str] = frozenset()
    locked_values: Mapping[str, object] = field(default_factory=dict)
    forced_candidate_count: int | None = None
    ignored_risk_factors: frozenset[str] = frozenset()

    # {
    # 責務: [__post_init__: GuardSettingsのbudget上限を検証する]
    # 処理: [1: candidate overrideの有限範囲を検証する]
    # 引数: [self: guard settings]
    # 戻り値: []
    # }
    def __post_init__(self) -> None:
        for name, kind in (
            ("apply_mode", ApplyMode),
            ("intent_preservation", IntentPreservation),
            ("risk_tolerance", RiskTolerance),
            ("budget", ComputeBudget),
        ):
            object.__setattr__(self, name, kind(getattr(self, name)))
        if self.forced_candidate_count is not None and not 1 <= self.forced_candidate_count <= 16:
            raise ValueError("forced candidate count must be between 1 and 16")


# {
# 責務: [PromptRiskRequest: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
@dataclass(frozen=True)
class PromptRiskRequest:
    prompt: str
    content_mode: ContentMode
    settings: GuardSettings = GuardSettings()
    negative_prompt: str = ""
    backend: str = ""
    model: str = ""
    model_family: str = ""
    task: str = "txt2img"
    negative_supported: bool = True
    loras: tuple[tuple[str, float, str], ...] = ()
    parameters: Mapping[str, object] = field(default_factory=dict)
    structured_prompt: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    prior_failures: tuple[str, ...] = ()

    # {
    # 責務: [__post_init__: content modeを型付きenumへ正規化する]
    # 処理: [1: UI/JSON stringをContentModeへ変換する]
    # 引数: [self: risk request]
    # 戻り値: []
    # }
    def __post_init__(self) -> None:
        object.__setattr__(self, "content_mode", ContentMode(self.content_mode))
        if any(
            not name.strip()
            or not isinstance(weight, (int, float))
            or isinstance(weight, bool)
            or not math.isfinite(weight)
            for name, weight, _role in self.loras
        ):
            raise ValueError("LoRA entries require a name and finite strength")


# {
# 責務: [RiskFactor: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
@dataclass(frozen=True)
class RiskFactor:
    key: str
    severity: RiskLevel
    description: str
    confidence: float
    entities: tuple[str, ...] = ()


# {
# 責務: [PromptRiskReport: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
@dataclass(frozen=True)
class PromptRiskReport:
    content_mode: ContentMode
    overall_risk: RiskLevel
    risk_factors: tuple[RiskFactor, ...]
    affected_entities: tuple[str, ...]
    conflicting_constraints: tuple[str, ...]
    lora_conflicts: tuple[str, ...]
    backend_compatibility_risks: tuple[str, ...]
    suggested_adjustments: tuple[str, ...]
    confidence: float
    provenance: Mapping[str, object]


# {
# 責務: [PromptAdjustmentResult: prompt stability domain責務を提供する]
# フィールド: [契約、依存関係または処理状態]
# 処理: [user intentを維持し生成安定化を構成する]
# }
@dataclass(frozen=True)
class PromptAdjustmentResult:
    original_prompt: str
    adjusted_prompt: str
    original_negative_prompt: str
    adjusted_negative_prompt: str
    original_parameters: Mapping[str, object]
    adjusted_parameters: Mapping[str, object]
    original_candidate_count: int
    candidate_count: int
    backend_hint: str | None
    adjustment_log: tuple[str, ...]
    requires_preview: bool
    applied: bool
    retry_limit: int
    report: PromptRiskReport

    # {
    # 責務: [__post_init__: adjustment budgetを有限範囲へ検証する]
    # 処理: [candidate数1..16とretry数0..3を保証する]
    # 引数: [self: adjustment result]
    # 戻り値: []
    # }
    def __post_init__(self) -> None:
        if not 1 <= self.candidate_count <= 16 or not 1 <= self.original_candidate_count <= 16:
            raise ValueError("candidate counts must be between 1 and 16")
        if not 0 <= self.retry_limit <= 3:
            raise ValueError("retry limit must be between 0 and 3")


# {
# 責務: [GenerationEvaluation: candidate生成と評価のfeedbackを表現する]
# フィールド: [image, failure_types, score, accepted]
# 処理: [bounded retry/repair adapterへ評価結果を渡す]
# }
@dataclass(frozen=True)
class GenerationEvaluation:
    image: object
    score: float
    failure_types: tuple[str, ...] = ()
    accepted: bool = False
