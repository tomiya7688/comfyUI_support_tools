from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)


# {
#   責務: [_civitai_source_metadata: 選択版からtag候補に共通する出典情報を組み立てる]
#   処理: [作者, base model, API利用条件とtag種別をJSON保存可能なtupleへ写す]
#   引数: [metadata: 選択したCivitai version, tag_source: 候補の取得元]
#   戻り値: [tuple[tuple[str, bool | str | None], ...]: profileへ保存するsource metadata]
# }
def _civitai_source_metadata(
    metadata: CivitaiLoraVersionMetadata,
    tag_source: str,
) -> tuple[tuple[str, bool | str | None], ...]:
    """Build shared provenance fields for one Civitai tag source."""
    candidate = metadata.candidate
    return (
        ("tag_source", tag_source),
        ("model_name", candidate.model_name),
        ("version_name", candidate.version_name),
        ("creator", candidate.creator),
        ("base_model", candidate.base_model),
        ("allow_no_credit", candidate.allow_no_credit),
        ("allow_commercial_use", candidate.allow_commercial_use),
        ("allow_derivatives", candidate.allow_derivatives),
        ("allow_different_license", candidate.allow_different_license),
        ("model_mode", candidate.model_mode),
        ("version_status", metadata.status),
        ("availability", metadata.availability),
        ("trained_words_raw", metadata.raw_trained_words),
    )


# {
#   責務: [build_civitai_tag_source_asset: Civitai trainedWordsを共通source assetへ変換する]
#   処理: [version metadata, 出典URL, 利用条件flag, 分割tagとtrainedWords原文を保持して画像なしassetを作る]
#   引数: [metadata: Civitaiから取得した選択version metadata]
#   戻り値: [CharacterSourceAsset: Character tag previewへ渡すsource asset]
#   エラー: [ValueError: metadataが正しいcontractでない場合]
# }
def build_civitai_tag_source_asset(
    metadata: CivitaiLoraVersionMetadata,
) -> CharacterSourceAsset:
    """Build a provenance-bearing tag asset without fetching model files or images."""
    if not isinstance(metadata, CivitaiLoraVersionMetadata):
        raise ValueError("metadataはCivitaiLoraVersionMetadataで指定してください")
    candidate = metadata.candidate
    source_reference = f"civitai://models/{candidate.model_id}/versions/{candidate.version_id}"
    return CharacterSourceAsset(
        caption_file=f"{source_reference}/trainedWords",
        image_file=None,
        tags=metadata.trained_words,
        outfit_id=None,
        source_url=candidate.source_url,
        source_work_id=f"{candidate.model_id}:{candidate.version_id}",
        license_status="unknown",
        training_permission="unknown",
        source_metadata=_civitai_source_metadata(metadata, "trained_words"),
    )


# {
#   責務: [build_civitai_model_tag_source_asset: Civitai model tagsをmanual review用sourceにする]
#   処理: [選択versionのmodel tagsを画像なしassetへ写し, tag出典と利用条件を保存する]
#   引数: [metadata: 検索結果を含む選択version metadata]
#   戻り値: [CharacterSourceAsset: 人が分類するmodel tag候補]
#   エラー: [ValueError: metadataの型が不正な場合]
# }
def build_civitai_model_tag_source_asset(
    metadata: CivitaiLoraVersionMetadata,
) -> CharacterSourceAsset:
    """Build a provenance-bearing suggestion asset from curated Civitai model tags."""
    if not isinstance(metadata, CivitaiLoraVersionMetadata):
        raise ValueError("metadataはCivitaiLoraVersionMetadataで指定してください")
    candidate = metadata.candidate
    source_reference = f"civitai://models/{candidate.model_id}/versions/{candidate.version_id}"
    return CharacterSourceAsset(
        caption_file=f"{source_reference}/tags",
        image_file=None,
        tags=candidate.tags,
        outfit_id=None,
        source_url=candidate.source_url,
        source_work_id=f"{candidate.model_id}:{candidate.version_id}",
        license_status="unknown",
        training_permission="unknown",
        source_metadata=_civitai_source_metadata(metadata, "model_tags"),
    )


# {
#   責務: [build_civitai_tag_source_assets: 選択LoRA versionのmodel tagsとtrainedWordsをpreview sourceへ変換する]
#   処理: [model tagsがある場合は別assetを追加し, trainedWords assetと順序付きtupleで返す]
#   引数: [metadata: Civitaiから取得した選択version metadata]
#   戻り値: [tuple[CharacterSourceAsset, ...]: 手動分類するmetadata source一覧]
#   エラー: [ValueError: metadataの型が不正な場合]
# }
def build_civitai_tag_source_assets(
    metadata: CivitaiLoraVersionMetadata,
) -> tuple[CharacterSourceAsset, ...]:
    """Return separate model-tag and trained-word sources for manual review."""
    trained_words = build_civitai_tag_source_asset(metadata)
    model_tags = (
        (build_civitai_model_tag_source_asset(metadata),) if metadata.candidate.tags else ()
    )
    return (*model_tags, trained_words)
