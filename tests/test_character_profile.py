"""Tests for the immutable Character Profile schema contracts."""

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

from src.comfyui_support_tools.shared.contracts.character_id import (
    create_character_id,
    is_valid_character_id,
)
from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_source_asset import (
    CharacterSourceAsset,
)


# {
#   責務: [CharacterProfileContractTest: profile IDの安定性とschema制約を検証する]
#   フィールド: [unittest.TestCaseのassertion機能]
#   処理: [profile/outfit contractの既定値, 参照整合性, immutable性を検証する]
# }
class CharacterProfileContractTest(unittest.TestCase):
    """Keep registration contracts deterministic and independent of persistence."""

    # {
    #   責務: [test_generated_id_survives_display_name_changes: 名前変更後もIDが変わらないことを検証する]
    #   処理: [生成したstable IDでprofileを作り, 表示名だけ変更してIDとsource情報を比較する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_generated_id_survives_display_name_changes(self) -> None:
        created_at = datetime(2026, 11, 4, tzinfo=timezone.utc)
        outfit = CharacterOutfitProfile(
            outfit_id="school_uniform",
            name="School uniform",
            garment_traits=("blazer", "pleated skirt"),
            innerwear_traits=("undershirt",),
            source_image_ids=("image-1",),
            confidence=0.85,
            user_confirmed=True,
        )
        source = CharacterSourceAsset(
            "identity/ref.txt",
            "identity/ref.png",
            ("blue_hair",),
            None,
            "https://example.invalid/work/1",
            "work-1",
            "unknown",
            "unknown",
        )
        character_id = create_character_id()
        profile = CharacterProfile(
            character_id=character_id,
            display_name="Sample Character",
            aliases=("Sample",),
            core_traits=("blue_hair",),
            confirmed_core_traits=("blue_hair",),
            default_outfit_id=outfit.outfit_id,
            outfit_profiles=(outfit,),
            reference_image_ids=("image-1",),
            provenance=(source,),
            created_at=created_at,
            updated_at=created_at,
        )

        renamed = replace(profile, display_name="Renamed Character")

        self.assertTrue(is_valid_character_id(profile.character_id))
        self.assertTrue(profile.character_id.startswith("character_"))
        self.assertEqual(renamed.character_id, profile.character_id)
        self.assertEqual(profile.default_outfit_id, "school_uniform")
        self.assertEqual(profile.provenance, (source,))
        with self.assertRaises(FrozenInstanceError):
            profile.display_name = "Mutated"

    # {
    #   責務: [test_rejects_missing_or_duplicate_default_outfit: outfit参照の整合性を検証する]
    #   処理: [未登録default IDと重複outfit IDがValueErrorになることを確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_rejects_missing_or_duplicate_default_outfit(self) -> None:
        outfit = CharacterOutfitProfile("casual", "Casual")
        common = {"character_id": create_character_id(), "display_name": "Sample"}

        with self.assertRaises(ValueError):
            CharacterProfile(**common, default_outfit_id="missing")
        with self.assertRaises(ValueError):
            CharacterProfile(**common, outfit_profiles=(outfit, outfit))

    # {
    #   責務: [test_rejects_invalid_confidence_and_naive_timestamps: 数値範囲とtimestamp境界を検証する]
    #   処理: [NaN confidenceとtimezoneなしtimestampを拒否することを確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_rejects_invalid_confidence_and_naive_timestamps(self) -> None:
        with self.assertRaises(ValueError):
            CharacterOutfitProfile("casual", "Casual", confidence=float("nan"))
        with self.assertRaises(ValueError):
            CharacterProfile(
                create_character_id(),
                "Sample",
                created_at=datetime(2026, 11, 4),
            )
        with self.assertRaises(ValueError):
            CharacterProfile(
                create_character_id(),
                "Sample",
                created_at=datetime(2026, 11, 4, tzinfo=timezone(timedelta(hours=9))),
            )

    # {
    #   責務: [test_default_timestamps_share_a_single_utc_value: 既定timestampが同一UTC時刻になることを検証する]
    #   処理: [timestampを省略したprofileのcreated_atとupdated_atが同値かつUTCであることをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_default_timestamps_share_a_single_utc_value(self) -> None:
        profile = CharacterProfile(create_character_id(), "Sample")

        self.assertEqual(profile.updated_at, profile.created_at)
        self.assertEqual(profile.created_at.utcoffset(), timedelta(0))


if __name__ == "__main__":
    unittest.main()
