"""Tests for explicit-root Character Profile JSON persistence."""

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.data.processing.character_profile_store import (
    CharacterProfileStore,
)
from src.comfyui_support_tools.shared.contracts.character_id import create_character_id
from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_reference_image import (
    CharacterReferenceImage,
)
from src.comfyui_support_tools.shared.contracts.character_source_asset import (
    CharacterSourceAsset,
)


# {
#   責務: [CharacterProfileStoreTest: explicit root保存のround-tripとschema安全性を検証する]
#   フィールド: [unittest.TestCaseのassertion機能]
#   処理: [JSON versioning, atomic replacement, ID/path境界, data integrityを検証する]
# }
class CharacterProfileStoreTest(unittest.TestCase):
    """Use temporary roots and never read or write user profile data."""

    # {
    #   責務: [_make_profile: round-trip用CharacterProfile fixtureを構築する]
    #   処理: [Unicode名, outfit, provenance, UTC timestampを含むimmutable profileを返す]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: [CharacterProfile: test profile]
    # }
    def _make_profile(self) -> CharacterProfile:
        timestamp = datetime(2026, 11, 4, 5, 0, tzinfo=timezone.utc)
        outfit = CharacterOutfitProfile(
            outfit_id="casual",
            name="普段着",
            garment_traits=("white shirt", "skirt"),
            innerwear_traits=("camisole",),
            visibility_rules=("only_when_visible",),
            source_image_ids=("image-1",),
            confidence=0.75,
            user_confirmed=True,
        )
        source = CharacterSourceAsset(
            "identity/ref.txt",
            "identity/ref.png",
            ("silver hair", "blue eyes"),
            None,
            "https://example.invalid/works/1",
            "work-1",
            "unknown",
            "unknown",
        )
        return CharacterProfile(
            character_id=create_character_id(),
            display_name="ユキ",
            aliases=("Snow",),
            core_traits=("silver hair", "blue eyes"),
            confirmed_core_traits=("silver hair",),
            rejected_traits=("red eyes",),
            default_outfit_id="casual",
            outfit_profiles=(outfit,),
            reference_image_ids=(f"sha256-{'a' * 64}",),
            reference_images=(
                CharacterReferenceImage(
                    image_id=f"sha256-{'a' * 64}",
                    source_path=str(Path.cwd() / "reference" / "yuki.png"),
                    content_sha256="a" * 64,
                ),
            ),
            provenance=(source,),
            created_at=timestamp,
            updated_at=timestamp,
        )

    # {
    #   責務: [test_profile_round_trip_preserves_nested_data: profile JSON保存/読込の全field保持を検証する]
    #   処理: [profileを保存してversionと復元結果を比較する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_profile_round_trip_preserves_nested_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = CharacterProfileStore(Path(temporary_directory) / "characters")
            profile = self._make_profile()

            saved_path = store.save(profile)
            document = json.loads(saved_path.read_text(encoding="utf-8"))

            self.assertEqual(document["schema_version"], 1)
            self.assertEqual(store.load(profile.character_id), profile)
            self.assertIn("ユキ", saved_path.read_text(encoding="utf-8"))

    # {
    #   責務: [test_save_replaces_existing_profile: 同一stable IDの更新保存を検証する]
    #   処理: [display nameとupdated_atを変えた同一ID profileで保存先が更新されることを確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_save_replaces_existing_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = CharacterProfileStore(temporary_directory)
            original = self._make_profile()
            updated = replace(
                original,
                display_name="ユキ・改",
                updated_at=original.created_at + timedelta(minutes=1),
            )

            store.save(original)
            store.save(updated)

            self.assertEqual(store.load(original.character_id), updated)
            self.assertEqual(len(list(Path(temporary_directory).glob("*.json"))), 1)

    # {
    #   責務: [test_rejects_unsafe_id_and_unsupported_schema: filename traversalと未知schema拒否を検証する]
    #   処理: [不正IDと未対応schema versionを読み込み拒否する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_rejects_unsafe_id_and_unsupported_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = CharacterProfileStore(root)
            with self.assertRaises(ValueError):
                store.load("../outside")

            profile = self._make_profile()
            store.save(profile)
            path = root / f"{profile.character_id}.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            document["schema_version"] = 99
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "schema_version"):
                store.load(profile.character_id)

    # {
    #   責務: [test_rejects_corrupt_json_and_identity_mismatch: corrupt/mismatched dataを拒否する]
    #   処理: [JSON parse failureとfilename/profile ID不一致をValueErrorで拒否する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_rejects_corrupt_json_and_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = CharacterProfileStore(root)
            profile = self._make_profile()
            path = store.save(profile)
            document = json.loads(path.read_text(encoding="utf-8"))

            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON"):
                store.load(profile.character_id)

            path.write_bytes(b"\xff")
            with self.assertRaisesRegex(ValueError, "JSON"):
                store.load(profile.character_id)

            document["character_id"] = create_character_id()
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "character_id"):
                store.load(profile.character_id)


if __name__ == "__main__":
    unittest.main()
