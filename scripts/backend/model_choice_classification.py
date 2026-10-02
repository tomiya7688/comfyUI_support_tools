"""Classify a selected base-model entry against the active backend catalog."""

from __future__ import annotations

from src.comfyui_support_tools.shared.model_identity import (
    ModelClassification,
    ModelKind,
    classify_model,
)


_BASE_MODEL_KINDS = {
    "checkpoints": ModelKind.CHECKPOINT,
    "unets": ModelKind.UNET,
}


def classify_base_model_choice(
    model_name: str,
    choices: dict[str, list[str]],
) -> ModelClassification:
    """Classify a selected checkpoint/UNet without guessing ambiguous kinds."""
    name = model_name.strip()
    matching_kinds = {
        kind
        for category, kind in _BASE_MODEL_KINDS.items()
        if name and name in choices.get(category, [])
    }
    if len(matching_kinds) == 1:
        return classify_model(name, declared_kind=next(iter(matching_kinds)))
    if len(matching_kinds) > 1:
        inferred = classify_model(name)
        return ModelClassification(
            family=inferred.family,
            kind=ModelKind.UNKNOWN,
            family_reason=inferred.family_reason,
            kind_reason="Candidate appears in both checkpoint and UNet catalogs; model kind is ambiguous.",
        )
    return classify_model(name)


def describe_model_classification(result: ModelClassification) -> str:
    """Format the classification and its evidence for a compact UI label."""
    return (
        f"系統: {result.family.value} / 種別: {result.kind.value}　"
        f"根拠: {result.family_reason} {result.kind_reason}"
    )
