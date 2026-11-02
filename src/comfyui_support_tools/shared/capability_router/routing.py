"""Explainable task and constraint router for local text-to-image capabilities."""

from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath

from .contracts import (
    CapabilityFeature,
    CapabilityRoute,
    GenerationCapability,
    GenerationIntent,
    GenerationUseCase,
    LatencyClass,
    ModelLifecycle,
    QualityClass,
)
from .registry import CapabilityRegistry


# {
#   責務: [CapabilityRouter: installedモデルを用途・資源・license・control制約に適合させる]
#   フィールド: [CapabilityRegistry, task evaluator ID map]
#   処理: [eligibleなfamily候補とfallback chainを理由付きで決定し, quality値を捏造しない]
# }
class CapabilityRouter:
    # {
    #   責務: [__init__: use-case evaluator IDをoptional登録する]
    #   処理: [retain an injected registry and evaluator mapping]
    #   引数: [registry: declarative model capability registry, evaluator_ids: task-use-case to evaluator ID]
    #   戻り値: []
    # }
    def __init__(
        self,
        registry: CapabilityRegistry,
        evaluator_ids: dict[GenerationUseCase, str] | None = None,
    ) -> None:
        self._registry = registry
        self._evaluator_ids = dict(evaluator_ids or {})

    # {
    #   責務: [route: eligibility constraintsを満たすモデルと候補fallbackを返す]
    #   処理: [1: installed familiesを識別, 2: controls/license/offline/resourcesでfilter, 3: preference順に安定sort]
    #   引数: [intent: user task/constraints and installed models]
    #   戻り値: [CapabilityRoute: selected model, cross-family alternatives, evaluator and explanations]
    #   エラー: [LookupError: 制約を満たすmodelがない場合]
    # }
    def route(self, intent: GenerationIntent) -> CapabilityRoute:
        classified = [(model, self._registry.classify(model)) for model in intent.installed_models]
        classified = [(model, profile) for model, profile in classified if profile is not None]
        excluded: list[tuple[str, str]] = []
        eligible: list[tuple[str, GenerationCapability]] = []
        for model, profile in classified:
            reason = self._exclusion_reason(profile, intent, model)
            if reason:
                excluded.append((model, reason))
            else:
                eligible.append((model, profile))

        if intent.manual_model is not None:
            selected = next(
                (item for item in eligible if item[0] == intent.manual_model),
                None,
            )
            if selected is None:
                manual_profile = self._registry.classify(intent.manual_model)
                reason = (
                    self._exclusion_reason(manual_profile, intent, intent.manual_model)
                    if manual_profile
                    else "unknown model capability"
                )
                raise LookupError(
                    f"manual model is unavailable or conflicts with a required constraint: {reason}"
                )
            ordered = [selected, *(item for item in eligible if item != selected)]
            reason = "Honored the manual model override after validating hard resource and license constraints."
        else:
            ordered = sorted(eligible, key=lambda item: _rank(item[1], intent))
            if not ordered:
                raise LookupError(
                    "no installed model satisfies the requested generation capability constraints"
                )
            reason = _route_reason(ordered[0][1], intent)

        # Candidate lists prefer distinct model families for cross-family Best-of-N.
        candidates = []
        seen_families = set()
        for model, profile in ordered:
            family = profile.family.casefold()
            if family in seen_families:
                continue
            seen_families.add(family)
            candidates.append((model, profile))
            if len(candidates) == intent.candidate_count:
                break
        if not candidates:
            raise LookupError("no model candidates remain after family diversity filtering")
        selected_model, selected_capability = candidates[0]
        return CapabilityRoute(
            selected_model,
            selected_capability,
            tuple(candidates),
            self._evaluator_ids.get(intent.use_case),
            reason,
            tuple(excluded),
        )

    # {
    #   責務: [_exclusion_reason: profileを除外するhard constraintの最初の理由を返す]
    #   処理: [apply lifecycle, backend, workflow, use-case, license, control, resolution and resource gates]
    #   引数: [profile: classified model descriptor or unknown, intent: task/resource/license requirements]
    #   戻り値: [str | None: exclusion explanation or eligible]
    # }
    @staticmethod
    def _exclusion_reason(
        profile: GenerationCapability | None, intent: GenerationIntent, model_name: str
    ) -> str | None:
        if profile is None:
            return "model family is unknown or ambiguous"
        if profile.lifecycle in {
            ModelLifecycle.DISCOVERED,
            ModelLifecycle.LEGACY,
            ModelLifecycle.UNAVAILABLE,
        }:
            return f"model lifecycle is {profile.lifecycle.value}"
        if profile.backend.casefold() != intent.backend.casefold():
            return f"requires backend {profile.backend}"
        if profile.workflow_profile_id and not any(
            _normalize_workflow(workflow) == profile.workflow_profile_id.casefold()
            for workflow in intent.available_workflows
        ):
            return f"requires installed workflow profile {profile.workflow_profile_id}"
        if intent.use_case not in profile.recommended_use_cases:
            return f"not registered for use case {intent.use_case.value}"
        if intent.commercial_required and (
            profile.license.commercial_use is not True or not profile.license.verified
        ):
            return "commercial-use license evidence is absent or unverified"
        if intent.offline_required and not profile.local_only:
            return "offline-only use excludes this non-local capability"
        if intent.required_lora_family and (
            CapabilityFeature.LORA not in profile.features
            or intent.required_lora_family.casefold()
            not in {value.casefold() for value in profile.lora_families}
        ):
            return "required LoRA family is not declared compatible"
        missing_controls = intent.required_controls - profile.supported_controls
        if missing_controls:
            return f"required controls are unsupported: {', '.join(sorted(missing_controls))}"
        if (
            intent.transparency_required
            and CapabilityFeature.TRANSPARENT_RGBA not in profile.features
        ):
            return "transparent RGBA output is unsupported"
        if intent.text_rendering_required and CapabilityFeature.TYPOGRAPHY not in profile.features:
            return "typography capability is not declared"
        if (
            intent.resolution
            and profile.maximum_resolution
            and any(
                requested > maximum
                for requested, maximum in zip(
                    intent.resolution, profile.maximum_resolution, strict=True
                )
            )
        ):
            return "requested resolution exceeds the profile maximum"
        minimum_vram = _minimum_vram(profile, model_name)
        if minimum_vram is None and (
            not intent.allow_unverified_resource or intent.use_case is GenerationUseCase.LOW_VRAM
        ):
            return "minimum VRAM is unknown"
        if intent.available_vram_gib is None and not intent.allow_unverified_resource:
            return "available VRAM was not provided"
        if minimum_vram is not None and intent.available_vram_gib is not None:
            if intent.available_vram_gib < minimum_vram:
                return f"requires {minimum_vram:g} GiB VRAM"
        if profile.minimum_ram_gib is None and (
            not intent.allow_unverified_resource or intent.use_case is GenerationUseCase.LOW_VRAM
        ):
            return "minimum system RAM is unknown"
        if profile.minimum_ram_gib is not None and intent.available_ram_gib is not None:
            if intent.available_ram_gib < profile.minimum_ram_gib:
                return f"requires {profile.minimum_ram_gib:g} GiB system RAM"
        if intent.available_ram_gib is None and not intent.allow_unverified_resource:
            return "available system RAM was not provided"
        return None


# {
#   責務: [_normalize_workflow: workflow pathをprofile ID比較用のstemへ変換する]
#   処理: [normalize slash style and compare filename stem case-insensitively]
#   引数: [value: local workflow path or filename]
#   戻り値: [str: case-folded workflow stem]
# }
def _normalize_workflow(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).stem.casefold()


# {
#   責務: [_minimum_vram: installed quantized variantのdeclared memory requirementを選ぶ]
#   処理: [select a matching known precision requirement or profile default]
#   引数: [profile: capability descriptor, installed_models: local identifiers]
#   戻り値: [float | None: quantized or native minimum VRAM, unknownならNone]
# }
def _minimum_vram(profile: GenerationCapability, model_name: str) -> float | None:
    quantized_requirements = dict(profile.quantized_vram_gib)
    if not quantized_requirements:
        return profile.minimum_vram_gib
    quantized_tags = {
        "fp8": "fp8",
        "bf16": "bf16",
        "fp16": "fp16",
        "int8": "int8",
        "int4": "int4",
        "q8_0": "int8",
        "q4_k_m": "int4",
    }
    normalized = model_name.casefold().replace("-", "_").replace(".", "_")
    for tag, quantization in quantized_tags.items():
        if tag in normalized and quantization in quantized_requirements:
            return quantized_requirements[quantization]
    return profile.minimum_vram_gib


# {
#   責務: [_rank: lifecycle, use case class, latency/quality preferenceで安定順序を作る]
#   処理: [sort only declared metadata and never claim measured quality superiority]
#   引数: [profile: declared model capability, intent: requested task and preferences]
#   戻り値: [tuple: deterministic lifecycle/preference ranking key]
#   注意: [quality classはmanifest metadataであり, benchmark測定がなければwinnerと主張しない]
# }
def _rank(
    profile: GenerationCapability, intent: GenerationIntent
) -> tuple[int, int, int, int, str]:
    lifecycle_rank = {
        ModelLifecycle.RECOMMENDED: 0,
        ModelLifecycle.SUPPORTED: 1,
        ModelLifecycle.EXPERIMENTAL: 2,
        ModelLifecycle.DISCOVERED: 3,
        ModelLifecycle.LEGACY: 4,
        ModelLifecycle.UNAVAILABLE: 5,
    }[profile.lifecycle]
    latency_rank = _preference_rank(profile.latency_class, intent.latency_preference)
    quality_rank = _preference_rank(profile.quality_class, intent.quality_preference)
    return (
        lifecycle_rank,
        latency_rank,
        quality_rank,
        -len(profile.recommended_use_cases),
        profile.profile_id.casefold(),
    )


# {
#   責務: [_preference_rank: profile classとuser preferenceのdistanceを計算する]
#   処理: [compare ordinal declared classes and return absolute tier distance]
#   引数: [value: profile quality/latency tier, preference: requested tier]
#   戻り値: [int: absolute tier distance]
# }
def _preference_rank(value: Enum, preference: Enum) -> int:
    if preference in {QualityClass.UNKNOWN, LatencyClass.UNKNOWN}:
        return 0
    if isinstance(preference, QualityClass):
        order = {
            QualityClass.HIGH: 0,
            QualityClass.BALANCED: 1,
            QualityClass.DRAFT: 2,
            QualityClass.UNKNOWN: 3,
        }
    else:
        order = {
            LatencyClass.VERY_FAST: 0,
            LatencyClass.FAST: 1,
            LatencyClass.MEDIUM: 2,
            LatencyClass.SLOW: 3,
            LatencyClass.UNKNOWN: 4,
        }
    return abs(order[value] - order[preference])


# {
#   責務: [_route_reason: selected profileの用途とevidence制限を説明する]
#   処理: [describe declared use-case/workflow compatibility and evidence limits]
#   引数: [profile: selected capability, intent: requested use case]
#   戻り値: [str: human-readable routing explanation]
# }
def _route_reason(profile: GenerationCapability, intent: GenerationIntent) -> str:
    reasons = [f"{profile.family} is registered for {intent.use_case.value}"]
    if profile.workflow_profile_id:
        reasons.append(f"workflow profile {profile.workflow_profile_id}")
    if profile.license.license_id.casefold() == "unknown":
        reasons.append("license evidence is unknown")
    reasons.append(
        "quality ranking is descriptive metadata unless matching benchmark evidence exists"
    )
    return "; ".join(reasons) + "."
