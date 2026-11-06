"""Tests for metadata-only Civitai LoRA discovery."""

import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from src.comfyui_support_tools.applications.character_registry.api import (
    fetch_civitai_lora_version,
    search_civitai_loras,
)
from src.comfyui_support_tools.applications.character_registry.data.processing import (
    civitai_lora_catalog_client,
)
from src.comfyui_support_tools.applications.character_registry.process.processing.civitai_lora_tag_source_builder import (
    build_civitai_tag_source_asset,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import (
    CivitaiLoraCandidate,
)

_MODEL_PAGE = {
    "items": [
        {
            "id": 123,
            "name": "Character LoRA",
            "type": "LORA",
            "allowNoCredit": False,
            "allowCommercialUse": "Image",
            "allowDerivatives": True,
            "allowDifferentLicense": False,
            "creator": {"username": "artist"},
            "tags": ["character", "anime"],
            "modelVersions": [
                {"id": 456, "name": "v1", "baseModel": "SDXL 1.0"},
                {"id": 457, "name": "v2", "baseModel": "Pony"},
            ],
        }
    ],
    "metadata": {"nextCursor": "next|cursor"},
}


# {
#   責務: [CivitaiLoraCatalogTest: public API clientの変換, 条件保存, 異常系を検証する]
#   フィールド: [unittest assertion機能]
#   処理: [合成responseを注入してネットワークなしでcandidate検索とversion取得を検証する]
# }
class CivitaiLoraCatalogTest(unittest.TestCase):
    """Keep API mapping coverage independent of Civitai availability."""

    # {
    #   責務: [test_search_returns_each_version_and_preserves_permissions: 各版と権利情報を確認する]
    #   処理: [search responseを注入し, query/cursor/利用条件/base model/URLを検証する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(civitai_lora_catalog_client, "_read_json", return_value=_MODEL_PAGE)
    def test_search_returns_each_version_and_preserves_permissions(self, read_json) -> None:
        candidates, next_cursor = search_civitai_loras("Aoba Moca", limit=8)

        self.assertEqual(len(candidates), 2)
        self.assertEqual(next_cursor, "next|cursor")
        self.assertEqual(candidates[0].base_model, "SDXL 1.0")
        self.assertEqual(candidates[1].base_model, "Pony")
        self.assertFalse(candidates[0].allow_no_credit)
        self.assertEqual(candidates[0].allow_commercial_use, "Image")
        self.assertTrue(candidates[0].allow_derivatives)
        self.assertFalse(candidates[0].allow_different_license)
        self.assertEqual(candidates[0].creator, "artist")
        self.assertEqual(
            candidates[0].source_url, "https://civitai.com/models/123?modelVersionId=456"
        )
        requested_url = read_json.call_args.args[0]
        self.assertIn("types=LORA", requested_url)
        self.assertIn("query=Aoba+Moca", requested_url)

    # {
    #   責務: [test_search_uses_cursor_on_followup_page: 続き検索にopaque cursorを渡す]
    #   処理: [search request URLにcursorがencodeされることを検証する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(civitai_lora_catalog_client, "_read_json", return_value=_MODEL_PAGE)
    def test_search_uses_cursor_on_followup_page(self, read_json) -> None:
        search_civitai_loras("Aoba", cursor="opaque:cursor")
        self.assertIn("cursor=opaque%3Acursor", read_json.call_args.args[0])

    # {
    #   責務: [test_missing_permissions_remain_unknown: 未提供の利用条件をunknownとして保つ]
    #   処理: [permission fieldのない候補を作り, 全permissionがNoneになることを検証する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(
        civitai_lora_catalog_client,
        "_read_json",
        return_value={
            "items": [
                {
                    "id": 1,
                    "name": "No permissions",
                    "type": "LORA",
                    "creator": {"username": "artist"},
                    "tags": [],
                    "modelVersions": [{"id": 2, "name": "v1", "baseModel": "SDXL"}],
                }
            ]
        },
    )
    def test_missing_permissions_remain_unknown(self, _read_json) -> None:
        candidates, _cursor = search_civitai_loras("sample")
        candidate = candidates[0]
        self.assertIsNone(candidate.allow_no_credit)
        self.assertIsNone(candidate.allow_commercial_use)
        self.assertIsNone(candidate.allow_derivatives)
        self.assertIsNone(candidate.allow_different_license)

    # {
    #   責務: [test_rate_limit_is_reported_without_retry: 429を利用者へ伝え自動再試行しない]
    #   処理: [urlopenが429を返すとRuntimeErrorになり, 呼出回数が1回であることを確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(
        civitai_lora_catalog_client,
        "urlopen",
        side_effect=HTTPError("https://civitai.com/api/v1/models", 429, "rate limited", {}, None),
    )
    def test_rate_limit_is_reported_without_retry(self, urlopen) -> None:
        with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
            civitai_lora_catalog_client._read_json("https://civitai.com/api/v1/models")
        urlopen.assert_called_once()

    # {
    #   責務: [test_search_validates_query_and_limit: 不正な検索入力を拒否する]
    #   処理: [空query, 不正なlimit, 長すぎるcursorをValueErrorにする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    def test_search_validates_query_and_limit(self) -> None:
        for kwargs in ({"query": " "}, {"query": "a", "limit": 0}, {"query": "a", "limit": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                search_civitai_loras(**kwargs)
        with self.assertRaises(ValueError):
            search_civitai_loras("a", cursor="x" * 2049)

    # {
    #   責務: [test_version_metadata_contains_trained_words_and_checks_identity: trigger metadataとID照合を検証する]
    #   処理: [version responseを注入し, trigger wordsとversion/model ID検証を確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(
        civitai_lora_catalog_client,
        "_read_json",
        return_value={
            "id": 456,
            "modelId": 123,
            "trainedWords": ["aoba_moca", "bang_dream"],
            "status": "Published",
            "availability": "Public",
        },
    )
    def test_version_metadata_contains_trained_words_and_checks_identity(self, _read_json) -> None:
        candidate = CivitaiLoraCandidate(
            123,
            456,
            "Character LoRA",
            "v1",
            "artist",
            "SDXL 1.0",
            (),
            "https://civitai.com/models/123?modelVersionId=456",
            False,
            "Image",
            True,
            False,
            None,
        )

        metadata = fetch_civitai_lora_version(candidate)

        self.assertEqual(metadata.trained_words, ("aoba_moca", "bang_dream"))
        self.assertIsNone(metadata.raw_trained_words)
        self.assertEqual(metadata.status, "Published")
        self.assertEqual(metadata.candidate.allow_commercial_use, "Image")
        self.assertEqual(metadata.preview_images, ())

    # {
    #   責務: [test_version_metadata_keeps_safe_preview_references_without_fetching_images: 安全な画像参照だけを保持する]
    #   処理: [合成API responseから画像ID, CDN URL, 閲覧levelがmetadataへ写り, bytes取得が起きないことを確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(
        civitai_lora_catalog_client,
        "_read_json",
        return_value={
            "id": 456,
            "modelId": 123,
            "trainedWords": ["aoba_moca"],
            "status": "Published",
            "availability": "Public",
            "images": [
                {
                    "id": 789,
                    "url": "https://image.civitai.com/example/width=450/image.webp",
                    "nsfwLevel": 1,
                },
                {
                    "id": 789,
                    "url": "https://image.civitai.com/example/width=450/image.webp",
                    "nsfwLevel": 1,
                },
            ],
        },
    )
    def test_version_metadata_keeps_safe_preview_references_without_fetching_images(
        self, read_json
    ) -> None:
        candidate = CivitaiLoraCandidate(
            123,
            456,
            "Character LoRA",
            "v1",
            "artist",
            "SDXL 1.0",
            (),
            "https://civitai.com/models/123?modelVersionId=456",
            False,
            "Image",
            True,
            False,
            None,
        )

        metadata = fetch_civitai_lora_version(candidate)

        self.assertEqual(len(metadata.preview_images), 1)
        self.assertEqual(metadata.preview_images[0].image_id, 789)
        self.assertEqual(metadata.preview_images[0].nsfw_level, 1)
        self.assertEqual(
            metadata.preview_images[0].url, "https://image.civitai.com/example/width=450/image.webp"
        )
        read_json.assert_called_once()

    # {
    #   責務: [test_version_metadata_rejects_non_civitai_preview_urls: 任意host画像URLを拒否する]
    #   処理: [悪意あるremote URLを含むAPI responseをRuntimeErrorにする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(
        civitai_lora_catalog_client,
        "_read_json",
        return_value={
            "id": 456,
            "modelId": 123,
            "trainedWords": [],
            "status": "Published",
            "availability": "Public",
            "images": [{"id": 789, "url": "https://example.invalid/image.webp", "nsfwLevel": 1}],
        },
    )
    def test_version_metadata_rejects_non_civitai_preview_urls(self, _read_json) -> None:
        candidate = CivitaiLoraCandidate(
            123,
            456,
            "Character LoRA",
            "v1",
            "artist",
            "SDXL 1.0",
            (),
            "https://civitai.com/models/123?modelVersionId=456",
            None,
            None,
            None,
            None,
            None,
        )
        with self.assertRaisesRegex(RuntimeError, "civitai.com"):
            fetch_civitai_lora_version(candidate)

    # {
    #   責務: [test_version_string_trained_words_are_split_and_preserved: comma区切りをtagへ分け原文をprovenanceに残す]
    #   処理: [Civitai string responseからmetadataとsource assetを作り, 分割tagとraw metadataを確認する]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(
        civitai_lora_catalog_client,
        "_read_json",
        return_value={
            "id": 456,
            "modelId": 123,
            "trainedWords": "  aoba_moca, bang_dream ,  ",
            "status": "Published",
            "availability": "Public",
        },
    )
    def test_version_string_trained_words_are_split_and_preserved(self, _read_json) -> None:
        """Split Civitai string tags and retain their exact source representation."""
        candidate = CivitaiLoraCandidate(
            123,
            456,
            "Character LoRA",
            "v1",
            "artist",
            "SDXL 1.0",
            (),
            "https://civitai.com/models/123?modelVersionId=456",
            False,
            "Image",
            True,
            False,
            None,
        )

        metadata = fetch_civitai_lora_version(candidate)
        source = build_civitai_tag_source_asset(metadata)

        self.assertEqual(metadata.trained_words, ("aoba_moca", "bang_dream"))
        self.assertEqual(metadata.raw_trained_words, "  aoba_moca, bang_dream ,  ")
        self.assertEqual(source.tags, ("aoba_moca", "bang_dream"))
        self.assertIn(
            ("trained_words_raw", "  aoba_moca, bang_dream ,  "),
            source.source_metadata,
        )

    # {
    #   責務: [test_version_rejects_mismatched_model_id: 別modelのversion metadataを拒否する]
    #   処理: [異なるmodelIdを返すAPI payloadをRuntimeErrorにする]
    #   引数: [self: unittest.TestCase instance]
    #   戻り値: []
    # }
    @patch.object(
        civitai_lora_catalog_client,
        "_read_json",
        return_value={"id": 456, "modelId": 999},
    )
    def test_version_rejects_mismatched_model_id(self, _read_json) -> None:
        candidate = CivitaiLoraCandidate(
            123,
            456,
            "Character LoRA",
            "v1",
            "artist",
            "SDXL 1.0",
            (),
            "https://civitai.com/models/123?modelVersionId=456",
            None,
            None,
            None,
            None,
            None,
        )
        with self.assertRaises(RuntimeError):
            fetch_civitai_lora_version(candidate)


if __name__ == "__main__":
    unittest.main()
