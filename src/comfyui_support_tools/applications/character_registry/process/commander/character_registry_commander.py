from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.process.messenger.character_profile_requests import (
    save_character_profile,
)
from src.comfyui_support_tools.applications.character_registry.process.messenger.character_source_requests import (
    load_character_sources,
)
from src.comfyui_support_tools.applications.character_registry.process.messenger.civitai_lora_catalog_requests import (
    load_selected_civitai_lora_version,
    search_civitai_lora_candidates,
    tag_selected_civitai_preview_images,
)
from src.comfyui_support_tools.applications.character_registry.process.processing.character_profile_registration_builder import (
    build_confirmed_character_profile,
)
from src.comfyui_support_tools.applications.character_registry.process.processing.character_tag_intake_processor import (
    build_character_tag_preview,
)
from src.comfyui_support_tools.applications.character_registry.process.processing.civitai_lora_tag_source_builder import (
    build_civitai_tag_source_assets,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_tag_intake_confirmation import (
    CharacterTagIntakeConfirmation,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import (
    CivitaiLoraCandidate,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)
from src.comfyui_support_tools.shared.contracts.inspector_contracts import TaggerSettings
from src.comfyui_support_tools.shared.contracts.civitai_preview_image import (
    MAX_TAGGER_ANALYSIS_IMAGES,
)


# {
#   責務: [search_civitai_loras: Character Registry内のCivitai LoRA検索を制御する]
#   処理: [検索条件をprocess messengerへ送り, 候補とpagination cursorを返す]
#   引数: [query: 検索語, limit: 1〜100件, cursor: opaque pagination token]
#   戻り値: [tuple[tuple[CivitaiLoraCandidate, ...], str | None]: version候補とcursor]
#   エラー: [ValueError: 入力不正, RuntimeError: 外部API失敗]
# }
def search_civitai_loras(
    query: str,
    limit: int,
    cursor: str | None,
) -> tuple[tuple[CivitaiLoraCandidate, ...], str | None]:
    return search_civitai_lora_candidates(query, limit, cursor)


# {
#   責務: [fetch_civitai_lora_version: 選択LoRA版のtrigger metadata取得を制御する]
#   処理: [選択candidateをprocess messengerへ送り, version metadataを返す]
#   引数: [candidate: 検索結果から選択したLoRA版]
#   戻り値: [CivitaiLoraVersionMetadata: trained wordsと公開状態]
#   エラー: [ValueError: candidate不正, RuntimeError: 外部API失敗またはID不一致]
# }
def fetch_civitai_lora_version(
    candidate: CivitaiLoraCandidate,
) -> CivitaiLoraVersionMetadata:
    return load_selected_civitai_lora_version(candidate)


# {
#   責務: [preview_character_intake: local/Civitai source取得とtag分類の処理順を調整する]
#   処理: [local sourceとCivitai metadataを取得し, 明示時だけpreview imageをloopback Taggerへ送り共通previewへ渡す]
#   引数: [request: intake request, civitai_candidate: 任意LoRA version, tagger_settings: 任意loopback設定]
#   戻り値: [CharacterTagIntakePreview: provenance付き分類候補]
# }
def preview_character_intake(
    request: CharacterTagIntakeRequest,
    civitai_candidate: CivitaiLoraCandidate | None = None,
    tagger_settings: TaggerSettings | None = None,
) -> CharacterTagIntakePreview:
    """Build a manual review preview from local captions and selected Civitai metadata."""
    assets, warnings = load_character_sources(request.dataset_root)
    if civitai_candidate is not None:
        metadata = load_selected_civitai_lora_version(civitai_candidate)
        assets = (*assets, *build_civitai_tag_source_assets(metadata))
        if tagger_settings is not None:
            assets = (*assets, *tag_selected_civitai_preview_images(metadata, tagger_settings))
        warnings = (
            *warnings,
            "Civitai model tagsとtrainedWordsは投稿者由来の候補です。画像で確認できた特徴とは限らないため、分類を確認してください。",
        )
        if (
            tagger_settings is not None
            and len(metadata.preview_images) > MAX_TAGGER_ANALYSIS_IMAGES
        ):
            warnings = (
                *warnings,
                f"Tagger解析は先頭{MAX_TAGGER_ANALYSIS_IMAGES}枚だけを対象にしました。候補画像のうち残りは未解析です。",
            )
    return build_character_tag_preview(request, assets, warnings)


# {
#   責務: [register_character_intake: 手動確認済みintake結果をprofileとして保存する]
#   処理: [確認済みprofileを構築し, process messenger経由で明示rootへ保存する]
#   引数: [preview: intake preview, confirmation: 人の分類確認, profile_directory: 設定から解決した保存先]
#   戻り値: [CharacterProfile: 保存済みprofile]
#   エラー: [ValueError: preview/confirmation不正, OSError: 保存失敗]
# }
def register_character_intake(
    preview: CharacterTagIntakePreview,
    confirmation: CharacterTagIntakeConfirmation,
    profile_directory: Path,
) -> CharacterProfile:
    if not isinstance(profile_directory, Path):
        raise ValueError("profile_directoryはpathlib.Pathで指定してください")
    profile = build_confirmed_character_profile(preview, confirmation)
    save_character_profile(profile, profile_directory)
    return profile
