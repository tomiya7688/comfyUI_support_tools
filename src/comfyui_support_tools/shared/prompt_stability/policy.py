"""Extensible model/content-mode stability policies and risk rule registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .contracts import ContentMode, PromptRiskRequest, RiskFactor

RiskRule = Callable[[PromptRiskRequest], tuple[RiskFactor, ...]]


# {
# 責務: [StabilityProfile: mode/model/backend単位のrisk ruleを保持する]
# フィールド: [content_mode, rule, compatibility_hints, negative_terms]
# 処理: [差し替え可能な安定化profileを構成する]
# }
@dataclass(frozen=True)
class StabilityProfile:
    content_mode: ContentMode
    rules: tuple[RiskRule, ...] = ()
    incompatible_families: tuple[str, ...] = ()
    preferred_backend: str = ""
    negative_terms: tuple[str, ...] = ()


# {
# 責務: [StabilityPolicyRegistry: profileをmodel/backend/content modeごとに解決する]
# フィールド: [profile登録table]
# 処理: [最も具体的なbackend/model-family profileを選択する]
# }
class StabilityPolicyRegistry:
    # {
    # 責務: [__init__: default SFW/NSFW profileを初期化する]
    # 処理: [1: baseline profileを構成する, 2: custom profileを登録する]
    # 引数: [self: registry, profiles: 追加profile]
    # 戻り値: []
    # }
    def __init__(self, profiles: tuple[StabilityProfile, ...] = ()) -> None:
        self._profiles: dict[tuple[ContentMode, str, str], StabilityProfile] = {}
        for mode in ContentMode:
            self.register(StabilityProfile(mode))
        for profile in profiles:
            self.register(profile)

    # {
    # 責務: [register: model-specific stability policyを追加する]
    # 処理: [1: profile keyを正規化する, 2: registryへ格納する]
    # 引数: [self: registry, profile: 登録profile, model_family: 任意model family, backend: 任意backend]
    # 戻り値: []
    # }
    def register(
        self, profile: StabilityProfile, *, model_family: str = "", backend: str = ""
    ) -> None:
        key = (profile.content_mode, model_family.casefold(), backend.casefold())
        self._profiles[key] = profile

    # {
    # 責務: [resolve: requestに適用するspecific profileを返す]
    # 処理: [1: backend/model/modeの最適一致を探す, 2: baselineへfallbackする]
    # 引数: [self: registry, request: risk request]
    # 戻り値: [profile: 適用profile]
    # }
    def resolve(self, request: PromptRiskRequest) -> StabilityProfile:
        family = request.model_family.casefold()
        backend = request.backend.casefold()
        for key in (
            (request.content_mode, family, backend),
            (request.content_mode, family, ""),
            (request.content_mode, "", backend),
            (request.content_mode, "", ""),
        ):
            if key in self._profiles:
                return self._profiles[key]
        raise LookupError(f"no stability profile for {request.content_mode.value}")
