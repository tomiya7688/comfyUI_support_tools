from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_tag_intake_confirmation import (
    CharacterTagIntakeConfirmation,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)


# {
#   責務: [build_confirmed_character_profile: intake previewと人の確認結果から保存profileを構築する]
#   処理: [確認済みidentity/outfitとpreview provenanceだけをCharacterProfileへ写す]
#   引数: [preview: 分類preview, confirmation: 人が選択したtrait/outfit]
#   戻り値: [CharacterProfile: 永続化可能なCharacterProfile]
#   エラー: [ValueError: preview/confirmationの型が不正な場合]
# }
def build_confirmed_character_profile(
    preview: CharacterTagIntakePreview,
    confirmation: CharacterTagIntakeConfirmation,
) -> CharacterProfile:
    if not isinstance(preview, CharacterTagIntakePreview):
        raise ValueError("previewはCharacterTagIntakePreviewで指定してください")
    if not isinstance(confirmation, CharacterTagIntakeConfirmation):
        raise ValueError("confirmationはCharacterTagIntakeConfirmationで指定してください")
    return CharacterProfile(
        character_id=preview.character_id,
        display_name=preview.display_name,
        aliases=preview.aliases,
        core_traits=confirmation.confirmed_identity_traits,
        confirmed_core_traits=confirmation.confirmed_identity_traits,
        rejected_traits=confirmation.rejected_traits,
        default_outfit_id=confirmation.default_outfit_id,
        outfit_profiles=confirmation.outfit_profiles,
        provenance=preview.source_assets,
    )
