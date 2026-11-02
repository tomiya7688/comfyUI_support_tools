"""Public LoRA composition analysis and export API."""

from .analysis import analyze_interference, check_composition_compatibility, factor_pairs
from .application import (
    CompositionComparisonEvaluator,
    CompositionEvaluator,
    LoRACompositionApplication,
)
from .contracts import (
    CompatibilityFinding,
    CompatibilityReport,
    EvaluationCase,
    EvaluationScore,
    LayerInterference,
    LoRAAdapter,
    LoRAComposition,
    LoRARole,
    MergeMethod,
    ScaleCandidate,
)
from .merge import merge_adapters

__all__ = [
    "CompatibilityFinding",
    "CompatibilityReport",
    "CompositionComparisonEvaluator",
    "CompositionEvaluator",
    "EvaluationCase",
    "EvaluationScore",
    "LayerInterference",
    "LoRAAdapter",
    "LoRAComposition",
    "LoRACompositionApplication",
    "LoRARole",
    "MergeMethod",
    "ScaleCandidate",
    "analyze_interference",
    "check_composition_compatibility",
    "factor_pairs",
    "merge_adapters",
]
