from src.comfyui_support_tools.applications.character_registry.data.messenger.civitai_lora_catalog_messenger import (
    load_civitai_lora_version as _load_civitai_lora_version,
)
from src.comfyui_support_tools.applications.character_registry.data.messenger.civitai_lora_catalog_messenger import (
    tag_civitai_preview_sources as _tag_civitai_preview_sources,
)
from src.comfyui_support_tools.applications.character_registry.data.messenger.civitai_lora_catalog_messenger import (
    search_civitai_lora_catalog as _search_civitai_lora_catalog,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import (
    CivitaiLoraCandidate,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)
from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset
from src.comfyui_support_tools.shared.contracts.inspector_contracts import TaggerSettings


# {
#   責務: [search_civitai_lora_candidates: process layerから候補検索をData layerへ配送する]
#   処理: [検索値をdata messengerへ渡し, candidateとcursorを返す]
#   引数: [query: 検索語, limit: 1〜100件, cursor: opaque pagination token]
#   戻り値: [tuple[tuple[CivitaiLoraCandidate, ...], str | None]: version候補とcursor]
#   エラー: [ValueError: 入力不正, RuntimeError: 外部API失敗]
# }
def search_civitai_lora_candidates(
    query: str,
    limit: int,
    cursor: str | None,
) -> tuple[tuple[CivitaiLoraCandidate, ...], str | None]:
    return _search_civitai_lora_catalog(query, limit, cursor)


# {
#   責務: [load_selected_civitai_lora_version: 選択したversion metadataをData layerから取得する]
#   処理: [candidateをdata messengerへ渡し, metadataを返す]
#   引数: [candidate: 選択済みLoRA版]
#   戻り値: [CivitaiLoraVersionMetadata: trained wordsと公開状態]
#   エラー: [ValueError: candidate不正, RuntimeError: 外部API失敗またはID不一致]
# }
def load_selected_civitai_lora_version(
    candidate: CivitaiLoraCandidate,
) -> CivitaiLoraVersionMetadata:
    return _load_civitai_lora_version(candidate)


# {
#   責務: [tag_selected_civitai_preview_images: Data境界へpreview画像のTagger処理を依頼する]
#   処理: [選択version metadataとTagger設定をdata messengerへ渡す]
#   引数: [metadata: 選択version metadata, settings: loopback Tagger settings]
#   戻り値: [tuple[CharacterSourceAsset, ...]: tagger候補とprovenanceを持つsource]
#   エラー: [ValueError: 設定またはsource不正, RuntimeError: 画像がない場合]
# }
def tag_selected_civitai_preview_images(
    metadata: CivitaiLoraVersionMetadata,
    settings: TaggerSettings,
) -> tuple[CharacterSourceAsset, ...]:
    return _tag_civitai_preview_sources(metadata, settings)
