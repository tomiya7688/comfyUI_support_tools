from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)


# {
#   責務: [build_civitai_tag_source_asset: Civitai trainedWordsを共通source assetへ変換する]
#   処理: [version metadata, 出典URL, 利用条件flagとtrigger wordsを保持し, 画像なしの候補assetを作る]
#   引数: [metadata: Civitaiから取得した選択version metadata]
#   戻り値: [CharacterSourceAsset: Character tag previewへ渡すsource asset]
#   エラー: [ValueError: metadataが正しいcontractでない場合]
# }
def build_civitai_tag_source_asset(
    metadata: CivitaiLoraVersionMetadata,
) -> CharacterSourceAsset:
    if not isinstance(metadata, CivitaiLoraVersionMetadata):
        raise ValueError("metadataはCivitaiLoraVersionMetadataで指定してください")
    candidate = metadata.candidate
    source_reference = f"civitai://models/{candidate.model_id}/versions/{candidate.version_id}"
    source_metadata: tuple[tuple[str, bool | str | None], ...] = (
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
    )
    return CharacterSourceAsset(
        caption_file=f"{source_reference}/trainedWords",
        image_file=None,
        tags=metadata.trained_words,
        outfit_id=None,
        source_url=candidate.source_url,
        source_work_id=f"{candidate.model_id}:{candidate.version_id}",
        license_status="unknown",
        training_permission="unknown",
        source_metadata=source_metadata,
    )
