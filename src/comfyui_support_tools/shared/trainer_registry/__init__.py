"""Runtime-verified registry for modern LoRA trainer integrations."""

from collections.abc import Mapping
from pathlib import Path

from .adapters import AIToolkitAdapter, RuntimeTrainerAdapter, SdScriptsAdapter, SimpleTunerAdapter
from .contracts import (
    AdapterMethod,
    ArchitectureProfile,
    ConfigValidation,
    Quantization,
    SmokeTestResult,
    SupportLevel,
    SupportMatrixEntry,
    TrainerProbe,
    TrainerResolution,
    TrainingProvenance,
    TrainingSpec,
)
from .profiles import architecture_profiles
from .registry import TrainerSupportRegistry, cache_fingerprint
from .smoke import SmokeGatedTraining, SmokeTestRunner


# {
# 責務: [default_trainer_registry: build the built-in extensible trainer adapter set]
# 処理: [bind optional local trainer roots/executables without installing or probing at import time]
# 引数: [trainer_roots: optional checkout directories, executables: optional command overrides, cache_path: optional support cache]
# 戻り値: [TrainerSupportRegistry: configured SimpleTuner, AI Toolkit and sd-scripts registry]
# }
def default_trainer_registry(
    trainer_roots: Mapping[str, str | Path] | None = None,
    executables: Mapping[str, str] | None = None,
    cache_path: str | Path | None = None,
    available_vram_gib: float | None = None,
) -> TrainerSupportRegistry:
    trainer_roots = trainer_roots or {}
    executables = executables or {}
    profiles = architecture_profiles()
    adapters = (
        SimpleTunerAdapter(
            trainer_roots.get("simpletuner"),
            executables.get("simpletuner"),
            profiles=profiles,
            available_vram_gib=available_vram_gib,
        ),
        AIToolkitAdapter(
            trainer_roots.get("ai_toolkit"),
            executables.get("ai_toolkit"),
            profiles=profiles,
            available_vram_gib=available_vram_gib,
        ),
        SdScriptsAdapter(
            trainer_roots.get("sd_scripts"),
            executables.get("sd_scripts"),
            profiles=profiles,
            available_vram_gib=available_vram_gib,
        ),
    )
    return TrainerSupportRegistry(adapters, profiles, cache_path)


__all__ = [
    "AIToolkitAdapter",
    "AdapterMethod",
    "ArchitectureProfile",
    "ConfigValidation",
    "Quantization",
    "RuntimeTrainerAdapter",
    "SdScriptsAdapter",
    "SimpleTunerAdapter",
    "SmokeGatedTraining",
    "SmokeTestResult",
    "SmokeTestRunner",
    "SupportLevel",
    "SupportMatrixEntry",
    "TrainerProbe",
    "TrainerResolution",
    "TrainerSupportRegistry",
    "TrainingProvenance",
    "TrainingSpec",
    "architecture_profiles",
    "cache_fingerprint",
    "default_trainer_registry",
]
