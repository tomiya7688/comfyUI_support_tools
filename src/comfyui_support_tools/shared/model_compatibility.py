"""Conservative family-level compatibility checks for LoRA and base models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .model_identity import ModelClassification, ModelFamily, ModelKind


# {
# 責務: [CompatibilityStatus: family-level LoRA判定結果の3状態を表す]
# フィールド: [compatible, incompatible, unknown]
# }
class CompatibilityStatus(str, Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


# {
# 責務: [CompatibilityResult: 互換性statusと根拠messageを返す]
# フィールド: [status: CompatibilityStatus, reason: 判定根拠]
# }
@dataclass(frozen=True)
class CompatibilityResult:
    status: CompatibilityStatus
    reason: str


# {
#   責務: [check_lora_compatibility: LoRAとbase modelのkind/familyを保守的に照合する]
#   処理: [kind不一致やunknown familyはunknown、既知family差はincompatible、family一致はcompatibleを返す]
#   引数: [lora: LoRA classification, base_model: checkpointまたはUNet classification]
#   戻り値: [CompatibilityResult: statusとreason]
# }
def check_lora_compatibility(
    lora: ModelClassification,
    base_model: ModelClassification,
) -> CompatibilityResult:
    """Compare recognized model families without treating unknown as a match."""
    if lora.kind is not ModelKind.LORA:
        return CompatibilityResult(
            CompatibilityStatus.UNKNOWN,
            f"The adapter kind is {lora.kind.value}, not LoRA.",
        )
    if base_model.kind not in {ModelKind.CHECKPOINT, ModelKind.UNET}:
        return CompatibilityResult(
            CompatibilityStatus.UNKNOWN,
            f"The base model kind is {base_model.kind.value}; expected checkpoint or UNet.",
        )
    if ModelFamily.UNKNOWN in {lora.family, base_model.family}:
        return CompatibilityResult(
            CompatibilityStatus.UNKNOWN,
            "Cannot compare model families: "
            f"LoRA: {lora.family_reason} Base model: {base_model.family_reason}",
        )
    if lora.family is not base_model.family:
        return CompatibilityResult(
            CompatibilityStatus.INCOMPATIBLE,
            f"LoRA family {lora.family.value} does not match "
            f"base model family {base_model.family.value}. "
            f"LoRA: {lora.family_reason} Base model: {base_model.family_reason}",
        )
    return CompatibilityResult(
        CompatibilityStatus.COMPATIBLE,
        f"Both models are identified as {lora.family.value}; this is a family-level match. "
        f"LoRA: {lora.family_reason} Base model: {base_model.family_reason}",
    )
