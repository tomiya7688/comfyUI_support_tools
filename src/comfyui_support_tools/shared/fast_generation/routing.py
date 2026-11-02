"""Compatibility-first routing for fast-generation model variants."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .contracts import (
    FastModelProfile,
    FastRouteRequest,
    FastRouteResult,
    GenerationMode,
    ModelCapability,
    Quantization,
)


# {
#   責務: [FastGenerationRouter: 利用可能variantとruntime資源からモデルを選択する]
#   フィールド: [profiles: immutableな候補profile]
#   処理: [明示モデルを尊重し, resource・backend・用途条件が不明または不適合な自動選択を拒否する]
# }
class FastGenerationRouter:
    # {
    #   責務: [__init__: profile IDの重複を検証してrouterを初期化する]
    #   引数: [profiles: route可能なmodel variant descriptor]
    #   戻り値: []
    # }
    def __init__(self, profiles: Iterable[FastModelProfile]) -> None:
        self._profiles = tuple(profiles)
        ids = [profile.profile_id.casefold() for profile in self._profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("fast generation profile IDs must be unique")

    # {
    #   責務: [route: 要求条件を満たす最初の利用可能variantを選ぶ]
    #   処理: [installed model・backend・intent・VRAM/RAM・quantizationを満たす候補に絞る]
    #   引数: [request: runtime資源, installed models, intent, mode, optional explicit model]
    #   戻り値: [FastRouteResult: 選択modelと適用quantization]
    #   エラー: [LookupError: 資源不足・未知情報・対応variantなしの場合]
    # }
    def route(self, request: FastRouteRequest) -> FastRouteResult:
        candidates = []
        for name in request.available_models:
            profile = _classify(name, self._profiles)
            if profile is not None:
                candidates.append((name, profile))
        if request.explicit_model is not None:
            selected = next(
                (item for item in candidates if item[0] == request.explicit_model), None
            )
            if selected is None:
                raise LookupError("explicit model is not a registered fast-generation variant")
            name, profile = selected
            precision_is_compatible, quantization = _compatible_quantization(profile, request, name)
            if (
                profile.backend.casefold() != request.resources.backend.casefold()
                or request.intent not in profile.intents
                or not _resources_fit(profile, request, quantization)
                or not precision_is_compatible
            ):
                raise LookupError(
                    "explicit fast-generation model does not fit the declared runtime resources"
                )
            return FastRouteResult(
                name, profile, quantization, "Honored the explicit compatible model selection."
            )

        if request.resources.gpu_vram_gib is None or request.resources.system_ram_gib is None:
            raise LookupError("automatic fast routing requires known GPU VRAM and system RAM")
        eligible = []
        for name, profile in candidates:
            compatible, quantization = _compatible_quantization(profile, request, name)
            if (
                compatible
                and request.intent in profile.intents
                and profile.backend.casefold() == request.resources.backend.casefold()
                and profile.fast_route
                and ModelCapability.TXT2IMG in profile.capabilities
                and _resources_fit(profile, request, quantization)
            ):
                eligible.append((name, profile, quantization))
        if not eligible:
            raise LookupError("no installed fast model variant fits the runtime resource profile")
        if request.mode is GenerationMode.QUALITY:
            raise LookupError("fast auto-routing is disabled in quality-priority mode")
        name, profile, quantization = min(
            eligible,
            key=lambda item: (
                item[1].experimental,
                -item[1].minimum_vram_gib,
                item[1].steps,
                item[1].profile_id,
            ),
        )
        return FastRouteResult(
            name,
            profile,
            quantization,
            f"Selected {profile.profile_id} using declared resource requirements and {request.intent.value} support; this is not a quality ranking.",
        )


# {
#   責務: [_resources_fit: 宣言済みmemory要件に対してruntime余裕を確認する]
#   引数: [profile: model resource declaration, request: observed runtime resources]
#   戻り値: [bool: both system RAM and VRAM have 1 GiB safety headroom]
# }
def _resources_fit(
    profile: FastModelProfile, request: FastRouteRequest, quantization: Quantization | None
) -> bool:
    resources = request.resources
    vram_requirement = dict(profile.minimum_vram_by_quantization).get(
        quantization, profile.minimum_vram_gib
    )
    return (
        resources.gpu_vram_gib is not None
        and resources.system_ram_gib is not None
        and (
            resources.available_vram_gib
            if resources.available_vram_gib is not None
            else resources.gpu_vram_gib
        )
        >= vram_requirement + 1
        and resources.system_ram_gib >= profile.minimum_ram_gib + 1
        and (
            resources.available_ram_gib is None
            or resources.available_ram_gib >= profile.minimum_ram_gib + 1
        )
    )


# {
#   責務: [_compatible_quantization: runtimeが宣言したprecisionの中からvariant対応値を選ぶ]
#   引数: [profile: model variant, request: hardware-supported quantizations, model: installed file name]
#   戻り値: [Quantization | None: declared precision, native precision, or no safe choice]
# }
def _compatible_quantization(
    profile: FastModelProfile, request: FastRouteRequest, model: str
) -> tuple[bool, Quantization | None]:
    declared = _filename_quantization(model)
    if declared is None:
        return True, None
    if declared not in profile.quantizations or declared not in request.resources.quantizations:
        return False, None
    return True, declared


# {
#   責務: [_filename_quantization: installed variant filenameから明示されたprecisionを読む]
#   引数: [model: checkpoint or UNet file name]
#   戻り値: [Quantization | None: explicit quant suffix or native/unmarked variant]
# }
def _filename_quantization(model: str) -> Quantization | None:
    normalized = _normalize(model)
    tokens = set(normalized.split())
    if "fp8" in tokens or "fp8e4m3" in tokens or "fp8e5m2" in tokens:
        return Quantization.FP8
    if "bf16" in tokens:
        return Quantization.BF16
    if "fp16" in tokens or "half" in tokens:
        return Quantization.FP16
    if "int8" in tokens or "q8 0" in normalized:
        return Quantization.INT8
    if "int4" in tokens or any(value in normalized for value in ("q4 k m", "q4 0", "q4km")):
        return Quantization.INT4
    return None


# {
#   責務: [_classify: 重複family aliasを最長token matchで一つのvariantへ解決する]
#   引数: [model_name: installed checkpoint name, profiles: registered descriptors]
#   戻り値: [FastModelProfile | None: unambiguous most-specific profile]
# }
def _classify(model_name: str, profiles: tuple[FastModelProfile, ...]) -> FastModelProfile | None:
    matches = [
        (len(_normalize(alias)), profile)
        for profile in profiles
        for alias in profile.aliases
        if _contains_alias(_normalize(model_name), _normalize(alias))
    ]
    if not matches:
        return None
    longest = max(length for length, _profile in matches)
    selected = {profile.profile_id: profile for length, profile in matches if length == longest}
    return next(iter(selected.values())) if len(selected) == 1 else None


# {
#   責務: [_normalize: filename variantをcase-insensitiveなspace-separated textに変換する]
#   引数: [value: model name or alias]
#   戻り値: [str: normalized identifier]
# }
def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


# {
#   責務: [_contains_alias: identifier内でaliasをtoken boundary付きで検索する]
#   引数: [identifier: normalized checkpoint name, alias: normalized profile alias]
#   戻り値: [bool: alias is present as complete tokens]
# }
def _contains_alias(identifier: str, alias: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", identifier) is not None
