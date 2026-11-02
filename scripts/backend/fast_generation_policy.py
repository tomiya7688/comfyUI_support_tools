"""Application adapter for resource-aware fast/draft model selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from comfyui_support_tools.shared.fast_generation import (
    FastGenerationRouter,
    FastRouteRequest,
    FastRouteResult,
    GenerationIntent,
    GenerationMode,
    Quantization,
    create_default_fast_model_profiles,
    probe_comfyui_resources,
)


# {
#   責務: [FastGenerationResolution: model, stepsとresource routeの理由を保持する]
#   フィールド: [checkpoint, steps, profile_id, quantization, total/free memory, device/CUDA metadata, reason]
# }
@dataclass(frozen=True, slots=True)
class FastGenerationResolution:
    checkpoint: str
    steps: int
    profile_id: str
    quantization: Quantization | None
    gpu_vram_gib: float | None
    system_ram_gib: float | None
    available_vram_gib: float | None
    available_ram_gib: float | None
    device_name: str | None
    cuda_available: bool | None
    cuda_version: str | None
    runtime_quantizations: frozenset[Quantization]
    reason: str


# {
#   責務: [resolve_fast_generation: observed ComfyUI resourcesとlocal model catalogからfast variantを選ぶ]
#   処理: [fast modeのみroutingし, explicit choiceを尊重してdeclared few-step設定を返す]
#   引数: [checkpoint: selected model, steps: user-selected steps, model_catalog: local choices, api_url: ComfyUI root, intent/mode: user preference, auto_route: optional route, has_explicit_model_overrides: workflow override guard, request_get: injectable HTTP GET]
#   戻り値: [FastGenerationResolution: checkpoint, steps, profile and explanation]
#   エラー: [LookupError: model/resource profile unavailable or incompatible]
# }
def resolve_fast_generation(
    checkpoint: str,
    steps: int,
    model_catalog: dict[str, list[str]],
    api_url: str,
    *,
    intent: GenerationIntent = GenerationIntent.PREVIEW,
    mode: GenerationMode = GenerationMode.FAST,
    auto_route: bool = False,
    has_explicit_model_overrides: bool = False,
    request_get: Callable[..., Any],
    quantizations: frozenset[Quantization] = frozenset(),
) -> FastGenerationResolution:
    if mode is GenerationMode.QUALITY:
        raise ValueError("fast-generation policy is disabled in quality-priority mode")
    if auto_route and has_explicit_model_overrides:
        raise ValueError(
            "fast model routing cannot override explicit ComfyUI workflow model selections"
        )
    resources = probe_comfyui_resources(api_url, request_get, quantizations)
    if resources.available_vram_gib is None or resources.available_ram_gib is None:
        raise LookupError("ComfyUI did not report currently available GPU VRAM and system RAM")
    available = tuple(
        dict.fromkeys([*model_catalog.get("checkpoints", []), *model_catalog.get("unets", [])])
    )
    result: FastRouteResult = FastGenerationRouter(create_default_fast_model_profiles()).route(
        FastRouteRequest(
            available,
            resources,
            intent=intent,
            mode=mode,
            explicit_model=None if auto_route else checkpoint,
        )
    )
    return FastGenerationResolution(
        result.model,
        result.profile.steps if mode is GenerationMode.FAST else steps,
        result.profile.profile_id,
        result.quantization,
        resources.gpu_vram_gib,
        resources.system_ram_gib,
        resources.available_vram_gib,
        resources.available_ram_gib,
        resources.device_name,
        resources.cuda_available,
        resources.cuda_version,
        resources.quantizations,
        result.reason,
    )
