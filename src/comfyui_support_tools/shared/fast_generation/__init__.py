"""Extensible contracts and resource-aware routing for fast generation."""

from .contracts import (
    FastModelProfile,
    FastRouteRequest,
    FastRouteResult,
    GenerationIntent,
    GenerationMode,
    ModelCapability,
    Quantization,
    RuntimeResources,
)
from .profiles import create_default_fast_model_profiles
from .routing import FastGenerationRouter
from .metrics import (
    GenerationHistory,
    GenerationMeasurement,
    GenerationSummary,
    quality_per_gib,
    quality_per_second,
    summarize_generation_history,
)
from .runtime import ComfyUIPeakMemorySampler, probe_comfyui_resources
from .pipeline import DraftBatchResult, ScoredDraft, run_draft_to_final

__all__ = [
    "FastGenerationRouter",
    "FastModelProfile",
    "ComfyUIPeakMemorySampler",
    "FastRouteRequest",
    "FastRouteResult",
    "DraftBatchResult",
    "GenerationIntent",
    "GenerationHistory",
    "GenerationMeasurement",
    "GenerationSummary",
    "GenerationMode",
    "ModelCapability",
    "Quantization",
    "RuntimeResources",
    "ScoredDraft",
    "create_default_fast_model_profiles",
    "probe_comfyui_resources",
    "quality_per_gib",
    "quality_per_second",
    "summarize_generation_history",
    "run_draft_to_final",
]
