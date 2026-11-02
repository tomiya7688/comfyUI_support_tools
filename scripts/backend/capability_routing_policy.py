"""Application adapter for intent-driven ComfyUI model and workflow selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from comfyui_support_tools.shared.capability_router import (
    CapabilityRegistry,
    CapabilityRoute,
    CapabilityRouter,
    GenerationUseCase,
    create_default_capabilities,
)
from comfyui_support_tools.shared.capability_router import (
    GenerationIntent as CapabilityIntent,
)
from comfyui_support_tools.shared.fast_generation import probe_comfyui_resources


# {
#   責務: [CapabilityRoutingResolution: selected model/workflowとobserved resource evidenceを保持する]
#   フィールド: [route, workflow, VRAM/RAM/device metadata]
# }
@dataclass(frozen=True, slots=True)
class CapabilityRoutingResolution:
    route: CapabilityRoute
    workflow: str
    available_vram_gib: float | None
    available_ram_gib: float | None
    device_name: str | None


# {
#   責務: [resolve_generation_capability: ComfyUI runtime/catalog情報で用途と制約に適合するcheckpoint/workflowを選択する]
#   処理: [実測可能なsystem_statsとinstalled namesをschemaへ写し, Routerの説明可能な判定を行う]
#   引数: [use_case: requested task, model_catalog: installed catalogs including workflow paths, api_url: ComfyUI endpoint, request_get: injectable HTTP client, resolution: requested dimensions, license/offline and candidate constraints]
#   戻り値: [CapabilityRoutingResolution: route and matching local workflow]
#   エラー: [LookupError: resource or installed compatible model/workflow is unavailable]
# }
def resolve_generation_capability(
    use_case: GenerationUseCase,
    model_catalog: dict[str, list[str]],
    api_url: str,
    *,
    request_get: Callable[..., Any],
    resolution: tuple[int, int],
    commercial_required: bool = False,
    offline_required: bool = False,
    allow_unverified_resource: bool = False,
    candidate_count: int = 1,
) -> CapabilityRoutingResolution:
    resources = probe_comfyui_resources(api_url, request_get)
    models = tuple(dict.fromkeys(model_catalog.get("checkpoints", [])))
    flows = tuple(model_catalog.get("flows", []))
    registry = CapabilityRegistry(create_default_capabilities())
    route = CapabilityRouter(registry).route(
        CapabilityIntent(
            use_case=use_case,
            backend="comfyui",
            installed_models=models,
            available_workflows=flows,
            available_vram_gib=resources.available_vram_gib,
            available_ram_gib=resources.available_ram_gib,
            commercial_required=commercial_required,
            offline_required=offline_required,
            text_rendering_required=use_case is GenerationUseCase.TYPOGRAPHY,
            transparency_required=use_case is GenerationUseCase.TRANSPARENT_ASSET,
            resolution=resolution,
            candidate_count=candidate_count,
            allow_unverified_resource=allow_unverified_resource,
        )
    )
    workflow_id = route.capability.workflow_profile_id
    workflow = (
        next(
            (value for value in flows if _workflow_stem(value) == workflow_id.casefold()),
            None,
        )
        if workflow_id
        else None
    )
    if workflow is None:
        raise LookupError(
            f"route selected {route.capability.profile_id}, but its installed workflow is unavailable"
        )
    return CapabilityRoutingResolution(
        route,
        workflow,
        resources.available_vram_gib,
        resources.available_ram_gib,
        resources.device_name,
    )


# {
#   責務: [_workflow_stem: workflow pathからprofile matching用stemを抽出する]
#   処理: [normalize Windows or POSIX separators before extracting filename stem]
#   引数: [value: installed workflow path]
#   戻り値: [str: case-folded stem]
# }
def _workflow_stem(value: str) -> str:
    return PurePosixPath(value.replace("\\", "/")).stem.casefold()
