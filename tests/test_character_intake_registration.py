"""Tests for saving manually confirmed Character Registry intake results."""

import tempfile
import unittest
from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.api import (
    register_character_intake,
)
from src.comfyui_support_tools.applications.character_registry.data.processing.character_profile_store import (
    CharacterProfileStore,
)
from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_outfit_tag_group import (
    CharacterOutfitTagGroup,
)
from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset
from src.comfyui_support_tools.shared.contracts.character_tag_candidate import (
    CharacterTagCandidate,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_confirmation import (
    CharacterTagIntakeConfirmation,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_preview import (
    CharacterTagIntakePreview,
)


# {
#   責務: [CharacterIntakeRegistrationTest: 明示確認済みtraitだけの登録とprovenance保存を検証する]
#   フィールド: [unittest assertion機能]
#   処理: [一時profile storeを使い, 手動確認と再読込の結果を確認する]
# }
class CharacterIntakeRegistrationTest(unittest.TestCase):
    """Keep profile registration and provenance persistence offline and isolated."""

    # {
    #   責務: [_preview: 登録テスト用のtag candidateとsource assetを作る]
    #   処理: [identity/outfit/contextを分類したpreviewを返す]
    #   引数: []
    #   戻り値: [CharacterTagIntakePreview: fixture preview]
    # }
    @staticmethod
    def _preview() -> CharacterTagIntakePreview:
        source = CharacterSourceAsset(
            caption_file="civitai://models/12/versions/34/trainedWords",
            image_file=None,
            tags=("blue_hair", "school_uniform"),
            outfit_id=None,
            source_url="https://civitai.com/models/12",
            source_work_id="12:34",
            license_status="unknown",
            training_permission="unknown",
            source_metadata=(("allow_commercial_use", "Image"), ("creator", "artist")),
        )
        return CharacterTagIntakePreview(
            character_id="registered_character",
            display_name="Registered Character",
            aliases=("RC",),
            identity_candidates=(
                CharacterTagCandidate("blue_hair", "identity", 1, 0.8, (source.caption_file,)),
            ),
            outfit_groups=(
                CharacterOutfitTagGroup(
                    outfit_id="unassigned",
                    is_unassigned=True,
                    tags=(
                        CharacterTagCandidate(
                            "school_uniform", "outfit", 1, 0.7, (source.caption_file,)
                        ),
                    ),
                ),
            ),
            context_candidates=(),
            unclassified_candidates=(),
            source_assets=(source,),
            warnings=("Civitai trigger候補は手動確認してください",),
        )

    # {
    #   責務: [test_register_saves_only_confirmed_identity_and_outfits: 手動確認後の保存とmetadata round-tripを検証する]
    #   処理: [profileを登録し, 再読込してidentity/outfit/source metadataを比較する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_register_saves_only_confirmed_identity_and_outfits(self) -> None:
        preview = self._preview()
        confirmed_outfit = CharacterOutfitProfile(
            outfit_id="school-uniform",
            name="School Uniform",
            garment_traits=("school_uniform",),
            user_confirmed=True,
        )
        confirmation = CharacterTagIntakeConfirmation(
            confirmed_identity_traits=("blue_hair",),
            rejected_traits=("temporary_unknown_trait",),
            outfit_profiles=(confirmed_outfit,),
            default_outfit_id="school-uniform",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            profile = register_character_intake(
                preview,
                confirmation,
                Path(temporary_directory),
            )
            restored = CharacterProfileStore(temporary_directory).load(profile.character_id)

        self.assertEqual(profile.confirmed_core_traits, ("blue_hair",))
        self.assertEqual(profile.outfit_profiles, (confirmed_outfit,))
        self.assertEqual(restored, profile)
        self.assertEqual(
            restored.provenance[0].source_metadata,
            (("allow_commercial_use", "Image"), ("creator", "artist")),
        )

    # {
    #   責務: [test_registration_rejects_existing_character_id: 登録時に既存profileを上書きしないことを検証する]
    #   処理: [同じcharacter IDを2回登録し, 2回目のFileExistsErrorと保存内容維持をassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_registration_rejects_existing_character_id(self) -> None:
        preview = self._preview()
        confirmation = CharacterTagIntakeConfirmation(confirmed_identity_traits=("blue_hair",))

        with tempfile.TemporaryDirectory() as temporary_directory:
            register_character_intake(preview, confirmation, Path(temporary_directory))
            with self.assertRaises(FileExistsError):
                register_character_intake(preview, confirmation, Path(temporary_directory))
            restored = CharacterProfileStore(temporary_directory).load(preview.character_id)

        self.assertEqual(restored.confirmed_core_traits, ("blue_hair",))

    # {
    #   責務: [test_confirmation_rejects_unconfirmed_outfit: 自動推定だけでoutfit登録させないことを検証する]
    #   処理: [user_confirmed=Falseのoutfitをconfirmationに渡し, ValueErrorをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_confirmation_rejects_unconfirmed_outfit(self) -> None:
        guessed_outfit = CharacterOutfitProfile(
            outfit_id="guessed-outfit",
            name="Guessed Outfit",
            garment_traits=("school_uniform",),
        )

        with self.assertRaises(ValueError):
            CharacterTagIntakeConfirmation(
                confirmed_identity_traits=("blue_hair",),
                outfit_profiles=(guessed_outfit,),
            )

    # {
    #   責務: [test_confirmation_rejects_contradictory_identity_decisions: 同じtraitのconfirm/reject競合を拒否する]
    #   処理: [identityとrejectedへ同じtagを渡し, ValueErrorをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_confirmation_rejects_contradictory_identity_decisions(self) -> None:
        with self.assertRaises(ValueError):
            CharacterTagIntakeConfirmation(
                confirmed_identity_traits=("blue_hair",),
                rejected_traits=("blue_hair",),
            )
