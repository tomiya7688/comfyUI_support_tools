"""Composable capability-based text-to-image model routing."""

from .benchmark import CapabilityBenchmarkCase, create_default_benchmark_matrix
from .candidates import (
    CapabilityCandidate,
    CrossFamilyCandidatePlan,
    run_cross_family_best_of_n,
)
from .contracts import (
    CapabilityFeature,
    CapabilityRoute,
    GenerationCapability,
    GenerationIntent,
    GenerationUseCase,
    LatencyClass,
    LicenseEvidence,
    ModelLifecycle,
    QualityClass,
)
from .evaluation import EvaluatorRegistry, GenerationEvaluator
from .profiles import create_default_capabilities
from .registry import CapabilityRegistry
from .routing import CapabilityRouter

__all__ = [
    "CapabilityBenchmarkCase",
    "CapabilityCandidate",
    "CapabilityFeature",
    "CapabilityRegistry",
    "CapabilityRoute",
    "CapabilityRouter",
    "CrossFamilyCandidatePlan",
    "EvaluatorRegistry",
    "GenerationCapability",
    "GenerationEvaluator",
    "GenerationIntent",
    "GenerationUseCase",
    "LatencyClass",
    "LicenseEvidence",
    "ModelLifecycle",
    "QualityClass",
    "create_default_benchmark_matrix",
    "create_default_capabilities",
    "run_cross_family_best_of_n",
]
