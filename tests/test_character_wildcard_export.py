import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.comfyui_support_tools.applications.character_registry import api
from src.comfyui_support_tools.applications.character_registry.api import (
    build_character_wildcard_files,
    write_character_wildcard_files,
)
from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile


# {
#   責務: [CharacterWildcardExportTests: CharacterProfileから生成するwildcard bundleの安全性を検証する]
#   処理: [確認済みidentity, outfit分離, wrapper参照, hidden trait除外を検証する]
#   フィールド: []
# }
class CharacterWildcardExportTests(unittest.TestCase):
    # {
    #   責務: [test_registration_export: 登録APIが出力するbundleを検証する]
    #   処理: [temp rootへexportし, character wildcardとLoRA呼び出しwrapperの本文を確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_registration_export_writes_character_and_lora_wrapper_files(self):
        profile = CharacterProfile(
            character_id="saved_character",
            display_name="Saved Character",
            confirmed_core_traits=("silver hair", "blue eyes"),
        )
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)

            written_paths = write_character_wildcard_files(profile, root)

            self.assertEqual(len(written_paths), 3)
            self.assertEqual(
                (root / "anime_character/saved_character/identity.txt").read_text(encoding="utf-8"),
                "silver hair, blue eyes\n",
            )
            self.assertEqual(
                (root / "anime_character/saved_character.txt").read_text(encoding="utf-8"),
                "__anime_character/saved_character/identity__\n",
            )
            self.assertEqual(
                (root / "character_with_lora/saved_character.txt").read_text(encoding="utf-8"),
                "__character_lora/saved_character__ __anime_character/saved_character__\n",
            )

    # {
    #   責務: [test_writer_rejects_parent_traversal: 出力pathのtraversal拒否を検証する]
    #   処理: [exporterの不正pathを模擬し, ValueErrorとoutside file未作成を確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_writer_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory) / "wildcards"
            outside_path = Path(directory) / "outside.txt"
            profile = CharacterProfile(
                character_id="safe_character",
                display_name="Safe Character",
                confirmed_core_traits=("silver hair",),
            )

            with patch.object(
                api,
                "_build_character_wildcard_files",
                return_value={"../outside.txt": "unsafe\n"},
            ):
                with self.assertRaisesRegex(ValueError, "parent traversal"):
                    write_character_wildcard_files(profile, root)

            self.assertFalse(outside_path.exists())

    # {
    #   責務: [test_exports_confirmed_traits_and_separate_outfits: 確認済み特徴と衣装を別wildcardに出力する]
    #   処理: [default outfit, 未確認outfit, innerwearを含むprofileをbundleへ変換する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_exports_confirmed_traits_and_separate_outfits(self):
        profile = CharacterProfile(
            character_id="character-123",
            display_name="Example Character",
            core_traits=("unconfirmed blue eyes",),
            confirmed_core_traits=(" blue hair ", "green eyes", "blue hair"),
            default_outfit_id="school",
            outfit_profiles=(
                CharacterOutfitProfile(
                    outfit_id="school",
                    name="School uniform",
                    outerwear_traits=("blazer",),
                    garment_traits=("pleated skirt",),
                    accessory_traits=("ribbon",),
                    innerwear_traits=("hidden camisole",),
                    user_confirmed=True,
                ),
                CharacterOutfitProfile(
                    outfit_id="casual",
                    name="Casual",
                    garment_traits=("hoodie",),
                    user_confirmed=False,
                ),
            ),
        )

        files = build_character_wildcard_files(profile)

        self.assertEqual(
            files["anime_character/character-123/identity.txt"],
            "blue hair, green eyes\n",
        )
        self.assertEqual(
            files["anime_character/character-123/outfit/school.txt"],
            "blazer, pleated skirt, ribbon\n",
        )
        self.assertEqual(
            files["anime_character/character-123.txt"],
            "__anime_character/character-123/identity__ "
            "__anime_character/character-123/outfit/school__\n",
        )
        self.assertEqual(
            files["character_with_lora/character-123.txt"],
            "__character_lora/character-123__ __anime_character/character-123__\n",
        )
        self.assertNotIn("hidden camisole", "".join(files.values()))
        self.assertNotIn("unconfirmed blue eyes", "".join(files.values()))
        self.assertNotIn("casual.txt", "".join(files))

    # {
    #   責務: [test_requires_confirmed_identity_traits: confirmed identityがないprofileを拒否する]
    #   処理: [未確認候補のみのprofileをexportしようとし, 分かりやすい入力エラーを確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_requires_confirmed_identity_traits(self):
        profile = CharacterProfile(character_id="empty", display_name="Empty")

        with self.assertRaisesRegex(ValueError, "確認済みidentity trait"):
            build_character_wildcard_files(profile)

    # {
    #   責務: [test_rejects_prompt_syntax_inside_traits: profile trait内のwildcard syntaxを拒否する]
    #   処理: [identity候補にnested referenceとinline choiceを渡し, export時の拒否を確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_rejects_prompt_syntax_inside_traits(self):
        profile = CharacterProfile(
            character_id="unsafe",
            display_name="Unsafe",
            confirmed_core_traits=("__other_character__",),
        )

        with self.assertRaisesRegex(ValueError, "wildcard記法"):
            build_character_wildcard_files(profile)


if __name__ == "__main__":
    unittest.main()
