"""Classify a selected base-model entry against the active backend catalog."""

from __future__ import annotations

from src.comfyui_support_tools.shared.model_identity import (
    ModelClassification,
    ModelKind,
    classify_model,
)
from .local_model_evidence import classify_local_model_choice


_BASE_MODEL_KINDS = {
    "checkpoints": ModelKind.CHECKPOINT,
    "unets": ModelKind.UNET,
}


# {
# 責務: [classify_base_model_choice: 選択中checkpointまたはUNetのmodel familyと種別を分類する]
# 処理: [1: catalog内のbase-model categoryを照合する, 2: 一意一致ならlocal evidenceで分類する,
# 3: 曖昧または未登録なら根拠を保ったfallback分類を返す]
# 引数: [model_name: 選択中model名, choices: backendのカテゴリ別catalog]
# 戻り値: [family・kindと分類根拠]
# }
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
        return classify_local_model_choice(name, next(iter(matching_kinds)))
    if len(matching_kinds) > 1:
        inferred = classify_model(name)
        return ModelClassification(
            family=inferred.family,
            kind=ModelKind.UNKNOWN,
            family_reason=inferred.family_reason,
            kind_reason="Candidate appears in both checkpoint and UNet catalogs; model kind is ambiguous.",
        )
    return classify_model(name)


# {
# 責務: [describe_model_classification: model分類結果と根拠をUI向けの短文にする]
# 処理: [1: family・kind・両分類根拠を連結する]
# 引数: [result: 表示するModelClassification]
# 戻り値: [UI label用の説明文]
# }
def describe_model_classification(result: ModelClassification) -> str:
    """Format the classification and its evidence for a compact UI label."""
    return (
        f"系統: {result.family.value} / 種別: {result.kind.value}　"
        f"根拠: {result.family_reason} {result.kind_reason}"
    )
