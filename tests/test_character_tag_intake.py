"""Tests for source-safe Character Registry tag intake."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.comfyui_support_tools.applications.character_registry.api import preview_character_intake
from src.comfyui_support_tools.applications.character_registry.data.processing import (
    tagged_dataset_reader,
)
from src.comfyui_support_tools.applications.character_registry.process.processing.character_tag_taxonomy import (
    classify_character_tag,
)
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)


# {
#   責務: [CharacterTagTaxonomyTest: identity/outfit/context分類境界を検証する]
#   フィールド: [unittest.TestCaseのassertion機能]
#   処理: [taxonomyが既知分類とunknown保留を行うことを検証する]
# }
class CharacterTagTaxonomyTest(unittest.TestCase):
    """Keep deterministic taxonomy behavior covered without external models."""

    # {
    #   責務: [test_identity_outfit_context_and_unknown_tags: taxonomyの分類結果を検証する]
    #   処理: [髪, 衣装, pose, 未知tagが各categoryへ分類されることをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_identity_outfit_context_and_unknown_tags(self) -> None:
        self.assertEqual(classify_character_tag("blue_hair"), "identity")
        self.assertEqual(classify_character_tag("t-shirt"), "outfit")
        self.assertEqual(classify_character_tag("school_uniform"), "outfit")
        self.assertEqual(classify_character_tag("looking_at_viewer"), "context")
        self.assertEqual(classify_character_tag("closed_eyes"), "context")
        self.assertEqual(classify_character_tag("rare_character_keyword"), "unclassified")


# {
#   責務: [CharacterTagIntakeTest: sidecar dataset previewの分離とprovenanceを検証する]
#   フィールド: [unittest.TestCaseのassertion機能]
#   処理: [identity/outfit/context grouping, unknown license, manifest path validationを検証する]
# }
class CharacterTagIntakeTest(unittest.TestCase):
    """Use isolated temporary data and never read user datasets."""

    # {
    #   責務: [test_preview_separates_categories_and_retains_unknown_provenance: previewの分類とprovenanceを検証する]
    #   処理: [fixture datasetを読み, tag分類とprovenance warningをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_preview_separates_categories_and_retains_unknown_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "identity").mkdir()
            (root / "outfits" / "school").mkdir(parents=True)
            (root / "identity" / "ref.png").write_bytes(b"fixture")
            (root / "identity" / "ref.txt").write_text(
                "blue_hair, blue_eyes, looking_at_viewer, rare_tag", encoding="utf-8-sig"
            )
            (root / "outfits" / "school" / "uniform.txt").write_text(
                "school_uniform, blue_skirt", encoding="utf-8"
            )
            manifest = {
                "assets": [
                    {
                        "caption_file": "identity/ref.txt",
                        "image_file": "identity/ref.png",
                        "source_url": "https://example.invalid/work/1",
                        "source_work_id": "work-1",
                        "license_status": None,
                        "training_permission": None,
                    }
                ]
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            preview = preview_character_intake(
                CharacterTagIntakeRequest("sample_character", "Sample", (), root)
            )

        self.assertEqual(
            {candidate.tag for candidate in preview.identity_candidates}, {"blue_hair", "blue_eyes"}
        )
        self.assertEqual(
            [candidate.tag for candidate in preview.context_candidates], ["looking_at_viewer"]
        )
        self.assertEqual(preview.outfit_groups[0].outfit_id, "school")
        self.assertEqual(
            [candidate.tag for candidate in preview.unclassified_candidates], ["rare_tag"]
        )
        self.assertEqual(preview.source_assets[0].source_work_id, "work-1")
        self.assertEqual(preview.source_assets[0].license_status, "unknown")
        self.assertTrue(any("権利情報" in warning for warning in preview.warnings))

    # {
    #   責務: [test_manifest_rejects_parent_traversal: manifestのdataset外参照を拒否する]
    #   処理: [parent traversalを含むmanifestを読み, ValueErrorをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_manifest_rejects_parent_traversal(self) -> None:
        invalid_references = (("../outside.txt", "inside.png"), ("inside.txt", "../outside.png"))
        for caption_file, image_file in invalid_references:
            with self.subTest(caption_file=caption_file, image_file=image_file):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    (root / "manifest.json").write_text(
                        json.dumps(
                            {"assets": [{"caption_file": caption_file, "image_file": image_file}]}
                        ),
                        encoding="utf-8",
                    )
                    (root / "inside.txt").write_text("blue_hair", encoding="utf-8")

                    with self.assertRaises(ValueError):
                        preview_character_intake(
                            CharacterTagIntakeRequest("sample_character", "Sample", (), root)
                        )

    # {
    #   責務: [test_manifest_outside_dataset_root_is_rejected: dataset外manifestを拒否する]
    #   処理: [manifestの解決先がroot外の場合, previewがValueErrorにすることをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_manifest_outside_dataset_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with patch.object(tagged_dataset_reader, "_is_inside_dataset", return_value=False):
                with self.assertRaises(ValueError):
                    preview_character_intake(
                        CharacterTagIntakeRequest("sample_character", "Sample", (), root)
                    )


if __name__ == "__main__":
    unittest.main()
