from dataclasses import replace

from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_tag_intake_confirmation import (
    CharacterTagIntakeConfirmation,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)


# {
#   責務: [build_confirmed_character_profile: intake previewと人の確認結果から保存profileを構築する]
#   処理: [確認済みidentity/outfit/reference imageをまとめ, outfit画像IDとpreview provenanceをprofileへ写す]
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
    image_ids_by_outfit: dict[str, list[str]] = {}
    for image in confirmation.reference_images:
        if image.outfit_assignment == "outfit" and image.outfit_id is not None:
            image_ids_by_outfit.setdefault(image.outfit_id, []).append(image.image_id)
    outfit_profiles = tuple(
        replace(
            outfit,
            source_image_ids=tuple(
                dict.fromkeys(
                    (*outfit.source_image_ids, *image_ids_by_outfit.get(outfit.outfit_id, ()))
                )
            ),
        )
        for outfit in confirmation.outfit_profiles
    )
    return CharacterProfile(
        character_id=preview.character_id,
        display_name=preview.display_name,
        aliases=preview.aliases,
        core_traits=confirmation.confirmed_identity_traits,
        confirmed_core_traits=confirmation.confirmed_identity_traits,
        rejected_traits=confirmation.rejected_traits,
        default_outfit_id=confirmation.default_outfit_id,
        outfit_profiles=outfit_profiles,
        reference_image_ids=tuple(image.image_id for image in confirmation.reference_images),
        reference_images=confirmation.reference_images,
        provenance=preview.source_assets,
    )
