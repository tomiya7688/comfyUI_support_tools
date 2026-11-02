"""Estimate character dataset readiness without blocking low-shot training."""

from comfyui_support_tools.shared.contracts.character_registry import (
    CharacterDatasetReadiness,
    CharacterProfile,
)


# {
#   責務: [assess_dataset_readiness: 画像品質/重複/outfit分布からtraining準備度を要約する]
#   処理: [1: training対象を選ぶ 2: exact hash重複を除いてeffective countを求める 3: warning/strategyを返す]
#   引数: [profile: character asset]
#   戻り値: [CharacterDatasetReadiness: non-blocking training readiness summary]
# }
def assess_dataset_readiness(profile: CharacterProfile) -> CharacterDatasetReadiness:
    selected = tuple(item for item in profile.image_refs if item.selected_for_training)
    unique_hashes = {item.sha256 for item in selected if item.sha256}
    duplicate_ratio = 0.0 if not selected else 1.0 - len(unique_hashes) / len(selected)
    qualities = [item.quality_score for item in selected if item.quality_score is not None]
    mean_quality = sum(qualities) / len(qualities) if qualities else None
    outfit_ids = {item.outfit_id for item in selected if item.outfit_id}
    quality_by_hash: dict[str, float] = {}
    for image in selected:
        if image.sha256:
            quality = image.quality_score if image.quality_score is not None else 1.0
            quality_by_hash[image.sha256] = max(quality_by_hash.get(image.sha256, 0.0), quality)
    effective_count = sum(quality_by_hash.values()) if qualities else float(len(unique_hashes))
    if len(selected) == 0:
        strategy = "no_selected_images"
    elif len(selected) <= 1:
        strategy = "one_shot"
    elif len(selected) <= 5:
        strategy = "low_shot"
    else:
        strategy = "standard"
    warnings = []
    if duplicate_ratio >= 0.25:
        warnings.append("high_duplicate_risk")
    if len(outfit_ids) == 1 and len(selected) >= 3:
        warnings.append("single_outfit_bias_risk")
    if mean_quality is not None and mean_quality < 0.45:
        warnings.append("low_average_image_quality")
    if len(selected) <= 1:
        warnings.append("manual_review_recommended")
    return CharacterDatasetReadiness(
        len(selected),
        effective_count,
        duplicate_ratio,
        mean_quality,
        len(outfit_ids),
        strategy,
        tuple(warnings),
    )
