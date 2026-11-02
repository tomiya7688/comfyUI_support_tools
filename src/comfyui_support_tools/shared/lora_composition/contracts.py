"""Typed inputs and outputs for LoRA composition workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# {
# 責務: [LoRARole: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class LoRARole(str, Enum):
    SUBJECT = "subject"
    CHARACTER = "character"
    STYLE = "style"
    CLOTHING = "clothing"
    EXPRESSION = "expression"
    POSE = "pose"
    OBJECT = "object"
    LIGHTING = "lighting"
    CONCEPT = "concept"
    SLIDER = "slider"


# {
# 責務: [MergeMethod: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class MergeMethod(str, Enum):
    WEIGHTED = "weighted"
    TOP_K = "top_k"
    K_LORA = "k_lora"
    ZIP_STYLE = "zip_style"
    ZIP_LORA = "zip_lora"


# {
# 責務: [LoRAAdapter: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class LoRAAdapter:
    """Loaded LoRA factors and the source evidence needed for safe merging."""

    name: str
    tensors: dict[str, Any]
    family: str
    architecture: str
    rank: int
    alpha: float
    role: LoRARole = LoRARole.CONCEPT
    provenance: dict[str, str] = field(default_factory=dict)
    slider_direction: str | None = None
    slider_minimum: float = -1.0
    slider_maximum: float = 1.0
    slider_neutral: float = 0.0


# {
# 責務: [CompatibilityFinding: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class CompatibilityFinding:
    """One preflight finding, with blocking and advisory states separated."""

    code: str
    message: str
    blocking: bool


# {
# 責務: [CompatibilityReport: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class CompatibilityReport:
    """Preflight result for a set of LoRAs and a requested base model."""

    compatible: bool
    base_model: str
    findings: tuple[CompatibilityFinding, ...]


# {
# 責務: [LayerInterference: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class LayerInterference:
    """Numerical similarity and conflict signals for one target module."""

    layer: str
    left: str
    right: str
    left_update_norm: float
    right_update_norm: float
    cosine_similarity: float
    subspace_overlap: float
    sign_conflict_fraction: float
    shared_layer: bool
    left_singular_values: tuple[float, ...]
    right_singular_values: tuple[float, ...]


# {
# 責務: [EvaluationScore: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class EvaluationScore:
    """Observable evaluator metrics for a fixed prompt and seed."""

    subject_fidelity: float
    style_fidelity: float
    prompt_controllability: float
    image_quality: float
    concept_presence: float = 0.0
    confusion: float = 0.0
    concept_binding: float = 0.0
    attribute_swap: float = 0.0
    leakage: float = 0.0
    anatomy: float = 0.0

    # {
    # 責務: [aggregate: perform the declared operation]
    # 処理: [follow the documented contract and preserve validated invariants]
    # 引数: [declared function inputs]
    # 戻り値: [declared function result]
    # }
    @property
    def aggregate(self) -> float:
        """Return a balanced score that penalizes weak constituent metrics."""
        core = (
            self.subject_fidelity,
            self.style_fidelity,
            self.prompt_controllability,
            self.image_quality,
        )
        bonus = (self.concept_presence + self.concept_binding + self.anatomy) / 6.0
        penalties = (self.confusion + self.attribute_swap + self.leakage) / 3.0
        return min(core) * 0.5 + sum(core) / len(core) * 0.5 + bonus - penalties


# {
# 責務: [EvaluationCase: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class EvaluationCase:
    """Validation prompt with a fixed seed for reproducible comparisons."""

    prompt: str
    seed: int
    negative_prompt: str = ""


# {
# 責務: [ScaleCandidate: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class ScaleCandidate:
    """A per-adapter and optional per-layer scale proposal."""

    global_scales: dict[str, float]
    layer_scales: dict[str, dict[str, float]]
    scores: tuple[EvaluationScore, ...]
    aggregate_score: float
    merge_method: MergeMethod | None = None


# {
# 責務: [LoRAComposition: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
@dataclass(frozen=True)
class LoRAComposition:
    """Portable recipe and optional static merged artifact description."""

    source_loras: tuple[str, ...]
    base_model: str
    merge_method: MergeMethod
    global_scales: dict[str, float]
    layer_scales: dict[str, dict[str, float]]
    score: float | None
    validation_prompts: tuple[EvaluationCase, ...]
    provenance: dict[str, Any]
    created_at: str
    static_merged_lora: Path | None = None
