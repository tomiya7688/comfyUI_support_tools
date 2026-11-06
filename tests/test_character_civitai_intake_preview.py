"""Tests for merging reviewed Civitai trigger metadata into Character tag intake."""

import unittest
from pathlib import Path
from unittest.mock import patch

from src.comfyui_support_tools.applications.character_registry.api import (
    preview_character_intake,
)
from src.comfyui_support_tools.applications.character_registry.process.commander import (
    character_registry_commander,
)
from src.comfyui_support_tools.shared.contracts.character_source_asset import CharacterSourceAsset
from src.comfyui_support_tools.shared.contracts.character_tag_intake_request import (
    CharacterTagIntakeRequest,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import (
    CivitaiLoraCandidate,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)


# {
#   責務: [CivitaiTagIntakePreviewTest: Civitai model tags/trainedWordsとlocal captionの統合previewを検証する]
#   フィールド: [unittest assertion機能]
#   処理: [外部APIをpatchし, identity/outfit/context/unclassified分類とsource provenanceを検証する]
# }
class CivitaiTagIntakePreviewTest(unittest.TestCase):
    """Keep Civitai metadata preview coverage independent of network and user datasets."""

    # {
    #   責務: [_candidate: API mapping testで使うCivitai version候補を作る]
    #   処理: [安定したID, 出典, base model, 利用条件flagを設定したcandidateを返す]
    #   引数: []
    #   戻り値: [CivitaiLoraCandidate: テスト用候補]
    # }
    @staticmethod
    def _candidate() -> CivitaiLoraCandidate:
        return CivitaiLoraCandidate(
            model_id=123,
            version_id=456,
            model_name="Character LoRA",
            version_name="v1",
            creator="artist",
            base_model="SDXL 1.0",
            tags=("shirt",),
            source_url="https://civitai.com/models/123?modelVersionId=456",
            allow_no_credit=False,
            allow_commercial_use="Image",
            allow_derivatives=True,
            allow_different_license=False,
            model_mode=None,
        )

    # {
    #   責務: [_metadata: candidateと分類テスト用trigger wordsを組み合わせる]
    #   処理: [代表的なidentity/outfit/context/unknown tagsを含むversion metadataを返す]
    #   引数: []
    #   戻り値: [CivitaiLoraVersionMetadata: テスト用version metadata]
    # }
    @classmethod
    def _metadata(cls) -> CivitaiLoraVersionMetadata:
        return CivitaiLoraVersionMetadata(
            candidate=cls._candidate(),
            trained_words=(
                "blue_hair",
                "school_uniform",
                "sitting",
                "custom_character_trigger",
            ),
            status="Published",
            availability="Public",
        )

    # {
    #   責務: [test_preview_combines_local_and_civitai_tags_with_provenance: source合流と分類を検証する]
    #   処理: [local sourceとCivitai metadataを注入し, preview groupと権利情報が保たれることをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_preview_combines_local_and_civitai_tags_with_provenance(self) -> None:
        request = CharacterTagIntakeRequest("sample_character", "Sample", (), Path("dataset"))
        local_asset = CharacterSourceAsset(
            "local/ref.txt",
            "local/ref.png",
            ("blue_hair", "shirt"),
            None,
            "https://source.example/work/1",
            "local-1",
            "unknown",
            "unknown",
        )
        with (
            patch.object(
                character_registry_commander,
                "load_selected_civitai_lora_version",
                return_value=self._metadata(),
            ) as load_civitai_version,
            patch.object(
                character_registry_commander,
                "load_character_sources",
                return_value=((local_asset,), ()),
            ) as load_local_sources,
        ):
            preview = preview_character_intake(request, self._candidate())

        identity = next(item for item in preview.identity_candidates if item.tag == "blue_hair")
        self.assertEqual(identity.count, 2)
        self.assertEqual(
            set(identity.source_files),
            {"local/ref.txt", "civitai://models/123/versions/456/trainedWords"},
        )
        outfit_group = next(group for group in preview.outfit_groups if group.is_unassigned)
        self.assertEqual({item.tag for item in outfit_group.tags}, {"school_uniform", "shirt"})
        shirt = next(item for item in outfit_group.tags if item.tag == "shirt")
        self.assertEqual(
            set(shirt.source_files),
            {"local/ref.txt", "civitai://models/123/versions/456/tags"},
        )
        self.assertEqual([item.tag for item in preview.context_candidates], ["sitting"])
        self.assertEqual(
            [item.tag for item in preview.unclassified_candidates], ["custom_character_trigger"]
        )

        civitai_sources = [
            asset for asset in preview.source_assets if asset.source_work_id == "123:456"
        ]
        self.assertEqual(len(civitai_sources), 2)
        for civitai_source in civitai_sources:
            self.assertIsNone(civitai_source.image_file)
            self.assertEqual(civitai_source.license_status, "unknown")
            self.assertEqual(civitai_source.training_permission, "unknown")
            self.assertEqual(civitai_source.source_url, self._candidate().source_url)
            self.assertIn(("allow_no_credit", False), civitai_source.source_metadata)
            self.assertIn(("allow_commercial_use", "Image"), civitai_source.source_metadata)
        model_tag_source = next(
            asset for asset in civitai_sources if asset.caption_file.endswith("/tags")
        )
        self.assertEqual(model_tag_source.tags, ("shirt",))
        self.assertIn(("tag_source", "model_tags"), model_tag_source.source_metadata)
        self.assertTrue(any("画像で確認" in warning for warning in preview.warnings))
        self.assertTrue(any("権利情報" in warning for warning in preview.warnings))
        load_civitai_version.assert_called_once_with(self._candidate())
        load_local_sources.assert_called_once_with(request.dataset_root)

    # {
    #   責務: [test_preview_without_civitai_keeps_existing_local_intake_path: 既存経路の互換性を検証する]
    #   処理: [候補なしpreviewでCivitai APIを呼ばずlocal tagsだけが返ることをassertする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(character_registry_commander, "load_selected_civitai_lora_version")
    @patch.object(
        character_registry_commander,
        "load_character_sources",
        return_value=((), ()),
    )
    def test_preview_without_civitai_keeps_existing_local_intake_path(
        self, _load_local_sources, load_civitai_version
    ) -> None:
        request = CharacterTagIntakeRequest("sample_character", "Sample", (), Path("dataset"))

        preview = preview_character_intake(request)

        self.assertEqual(preview.source_assets, ())
        self.assertEqual(preview.identity_candidates, ())
        load_civitai_version.assert_not_called()
