from src.comfyui_support_tools.applications.character_registry.data.processing.civitai_lora_catalog_client import (
    fetch_civitai_lora_version as _fetch_civitai_lora_version,
)
from src.comfyui_support_tools.applications.character_registry.data.processing.civitai_lora_catalog_client import (
    search_civitai_loras as _search_civitai_loras,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import (
    CivitaiLoraCandidate,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)


# {
#   責務: [search_civitai_lora_catalog: Data processingへLoRA候補検索を配送する]
#   処理: [query, page size, cursorをAPI clientへ渡し, 候補と続きcursorを返す]
#   引数: [query: 検索語, limit: 1〜100件, cursor: opaque pagination token]
#   戻り値: [tuple[tuple[CivitaiLoraCandidate, ...], str | None]: version候補とcursor]
#   エラー: [ValueError: 入力不正, RuntimeError: 外部API失敗]
# }
def search_civitai_lora_catalog(
    query: str,
    limit: int,
    cursor: str | None,
) -> tuple[tuple[CivitaiLoraCandidate, ...], str | None]:
    return _search_civitai_loras(query, limit=limit, cursor=cursor)


# {
#   責務: [load_civitai_lora_version: Data processingへ選択versionのmetadata取得を配送する]
#   処理: [選択済みcandidateをAPI clientへ渡し, trained wordsと公開状態を返す]
#   引数: [candidate: 選択済みLoRA版]
#   戻り値: [CivitaiLoraVersionMetadata: trained wordsと公開状態]
#   エラー: [ValueError: candidate不正, RuntimeError: 外部API失敗またはID不一致]
# }
def load_civitai_lora_version(
    candidate: CivitaiLoraCandidate,
) -> CivitaiLoraVersionMetadata:
    return _fetch_civitai_lora_version(candidate)
