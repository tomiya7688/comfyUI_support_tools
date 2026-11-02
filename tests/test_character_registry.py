"""Tests for stable character identity, prompt resolution, and local profile storage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from comfyui_support_tools.applications.character_registry.data.processing.character_store import (
    load_character_profile,
    resolve_character_reference,
    save_character_profile,
)
from comfyui_support_tools.applications.character_registry.data.processing.image_storage import (
    ImageStorageMode,
    preferred_training_image,
    register_character_image,
)
from comfyui_support_tools.applications.character_registry.process.processing.dataset_readiness import (
    assess_dataset_readiness,
)
from comfyui_support_tools.applications.character_registry.process.processing.prompt_resolver import (
    resolve_character_prompt,
    resolve_visibility,
)
from comfyui_support_tools.shared.contracts.character_registry import (
    CharacterImage,
    CharacterProfile,
    CharacterTrait,
    OutfitProfile,
    VisibilityContext,
)


# {
#   責務: [CharacterRegistryTests: identity/outfit/visibility/readiness/persistence behaviorを検証する]
#   フィールド: [profile fixturesと一時JSON storage]
# }
class CharacterRegistryTests(unittest.TestCase):
    # {
    #   責務: [test_custom_outfit_replaces_only_conflicting_category: user outfit指定で重複登録衣装だけ抑制する]
    #   処理: [1: profileを解決する 2: core/default outfit/custom overrideを照合する]
    #   引数: []
    #   戻り値: []
    # }
    def test_custom_outfit_replaces_only_conflicting_category(self):
        profile = CharacterProfile(
            "char_1",
            "A",
            core_traits=(CharacterTrait("hair", "blue hair"),),
            outfit_profiles=(
                OutfitProfile(
                    "uniform",
                    "Uniform",
                    traits=(
                        CharacterTrait("upper_body_clothing", "school blazer"),
                        CharacterTrait("footwear", "loafers"),
                    ),
                ),
            ),
            default_outfit_id="uniform",
        )
        result = resolve_character_prompt(
            profile,
            custom_traits=(CharacterTrait("upper_body_clothing", "rain coat"),),
        )
        self.assertEqual(result.traits, ("A", "blue hair", "loafers", "rain coat"))
        self.assertEqual(result.suppressed_categories, ("upper_body_clothing",))

    # {
    #   責務: [test_hidden_traits_are_omitted_without_visibility_evidence: uncertain innerwearを保守的に省く]
    #   処理: [1: evidenceなしと明示evidenceでvisibility policyを比較する]
    #   引数: []
    #   戻り値: []
    # }
    def test_hidden_traits_are_omitted_without_visibility_evidence(self):
        hidden = CharacterTrait("innerwear", "white camisole")
        omitted = resolve_visibility(hidden, VisibilityContext())
        visible = resolve_visibility(
            hidden,
            VisibilityContext(camera_signals=("high_camera",), pose_signals=("sitting",)),
        )
        self.assertEqual(omitted.action, "omit")
        self.assertEqual(visible.action, "inject")
        self.assertEqual(visible.confidence, 0.6)

    # {
    #   責務: [test_profile_roundtrip_uses_stable_id_and_optimistic_updates: display nameから独立してprofileを永続化する]
    #   処理: [1: profileを初回保存する 2: typed roundtripを確認する 3: tokenなしupdate拒否とtoken付きupdateを検証する]
    #   引数: []
    #   戻り値: []
    # }
    def test_profile_roundtrip_uses_stable_id_and_optimistic_updates(self):
        profile = CharacterProfile(
            "char_1",
            "Character A",
            aliases=("A",),
            core_traits=(CharacterTrait("hair", "silver hair", 0.95),),
            image_refs=(CharacterImage("img_1", "file:///a.png", "hash-1", quality_score=0.8),),
        )
        with tempfile.TemporaryDirectory() as directory:
            version = save_character_profile(Path(directory), profile)
            self.assertEqual(load_character_profile(Path(directory), "char_1"), profile)
            self.assertEqual(resolve_character_reference(Path(directory), "a"), profile)
            renamed = CharacterProfile(**{**profile.__dict__, "display_name": "New Name"})
            with self.assertRaises(FileExistsError):
                save_character_profile(Path(directory), renamed)
            self.assertNotEqual(
                save_character_profile(Path(directory), renamed, expected_hash=version), version
            )
            self.assertEqual(
                load_character_profile(Path(directory), "char_1").display_name, "New Name"
            )

    # {
    #   責務: [test_readiness_warns_on_duplicates_without_hard_minimum: low-shot候補を枚数だけで禁止しない]
    #   処理: [1: duplicate-heavy datasetを作る 2: effective count/strategy/warningを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_readiness_warns_on_duplicates_without_hard_minimum(self):
        profile = CharacterProfile(
            "char_1",
            "A",
            image_refs=(
                CharacterImage("1", "one", "same", quality_score=0.8),
                CharacterImage("2", "two", "same", quality_score=0.8),
                CharacterImage("3", "three", "other", quality_score=0.6),
            ),
        )
        result = assess_dataset_readiness(profile)
        self.assertEqual(result.suggested_strategy, "low_shot")
        self.assertEqual(result.selected_image_count, 3)
        self.assertAlmostEqual(result.effective_image_count, 1.4)
        self.assertIn("high_duplicate_risk", result.warnings)

    # {
    #   責務: [test_image_import_keeps_original_training_source_and_managed_preview: managed WebPをpreview用に追加する]
    #   処理: [1: synthetic originalを作る 2: Original + WebP登録する 3: source/hash/previewとtraining sourceを照合する]
    #   引数: []
    #   戻り値: []
    # }
    def test_image_import_keeps_original_training_source_and_managed_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.png"
            Image.new("RGBA", (24, 16), (255, 0, 0, 128)).save(source)
            image = register_character_image(
                source,
                root / "managed",
                "image_1",
                mode=ImageStorageMode.ORIGINAL_AND_WEBP,
            )
            training_path, warning = preferred_training_image(image)
            self.assertTrue(Path(training_path).is_file())
            self.assertEqual(Path(training_path).suffix, ".png")
            self.assertTrue(Path(image.managed_webp_uri).is_file())
            self.assertIsNone(warning)
            self.assertEqual((image.width, image.height), (24, 16))
            with self.assertRaises(FileExistsError):
                register_character_image(source, root / "managed", "image_2", known_images=(image,))


if __name__ == "__main__":
    unittest.main()
