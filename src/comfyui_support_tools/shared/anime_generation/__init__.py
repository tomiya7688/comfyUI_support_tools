"""Extensible anime and illustration model policies and routing."""

from .benchmark import AnimeBenchmarkCase, AnimeBenchmarkPrompt, build_benchmark_prompts
from .contracts import (
    AnimeContentMode,
    AnimeIntent,
    AnimeLoraRequirement,
    AnimeModelFamily,
    AnimeModelProfile,
    AnimePromptPolicy,
    AnimeRouteRequest,
    AnimeRouteResult,
    AnimeRoutingError,
)
from .policy import apply_anime_prompt_policy
from .profiles import create_default_anime_model_registry
from .routing import AnimeModelRegistry, classify_anime_model, route_anime_model

__all__ = [
    "AnimeBenchmarkCase",
    "AnimeBenchmarkPrompt",
    "AnimeContentMode",
    "AnimeIntent",
    "AnimeLoraRequirement",
    "AnimeModelFamily",
    "AnimeModelProfile",
    "AnimeModelRegistry",
    "AnimePromptPolicy",
    "AnimeRouteRequest",
    "AnimeRouteResult",
    "AnimeRoutingError",
    "apply_anime_prompt_policy",
    "build_benchmark_prompts",
    "classify_anime_model",
    "create_default_anime_model_registry",
    "route_anime_model",
]
