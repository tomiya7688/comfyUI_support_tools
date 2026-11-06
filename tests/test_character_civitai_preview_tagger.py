"""Tests for transient Civitai preview analysis through a local Tagger API."""

from email.message import Message
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image

from src.comfyui_support_tools.applications.character_registry.data.processing import (
    civitai_preview_tagger,
)
from src.comfyui_support_tools.shared.contracts.civitai_lora_candidate import CivitaiLoraCandidate
from src.comfyui_support_tools.shared.contracts.civitai_lora_version_metadata import (
    CivitaiLoraVersionMetadata,
)
from src.comfyui_support_tools.shared.contracts.civitai_preview_image import CivitaiPreviewImage
from src.comfyui_support_tools.shared.contracts.inspector_contracts import TaggerSettings


# {
#   責務: [_FakeResponse: urllib responseのbounded bodyとMIMEをテスト用に提供する]
#   フィールド: [body: response bytes, headers: MIME header]
# }
class _FakeResponse:
    """Provide the small response interface used by urllib transport code."""

    # {
    #   責務: [__init__: fake bodyとcontent typeを保持する]
    #   処理: [指定bytesからMIME headerを作る]
    #   引数: [self: fake response, body: response bytes, content_type: MIME type]
    #   戻り値: []
    # }
    def __init__(self, body: bytes, content_type: str):
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    # {
    #   責務: [__enter__: fake responseをcontext managerとして返す]
    #   処理: [selfを返す]
    #   引数: [self: fake response]
    #   戻り値: [_FakeResponse: 同じresponse]
    # }
    def __enter__(self):
        return self

    # {
    #   責務: [__exit__: fake response contextを閉じる]
    #   処理: [例外を抑止せずNoneを返す]
    #   引数: [self: fake response, exception tuple]
    #   戻り値: [None: 例外を抑止しない]
    # }
    def __exit__(self, *_exception):
        return None

    # {
    #   責務: [read: fake bodyを返す]
    #   処理: [要求されたbyte数までbodyを返す]
    #   引数: [self: fake response, amount: 最大byte数]
    #   戻り値: [bytes: fake response bytes]
    # }
    def read(self, amount: int) -> bytes:
        return self.body[:amount]


# {
#   責務: [_FakeOpener: image/CDNとloopback Tagger requestを記録して応答する]
#   フィールド: [image_bytes: fixture image, requests: 呼出履歴]
# }
class _FakeOpener:
    """Serve deterministic Civitai and Tagger responses without network access."""

    # {
    #   責務: [__init__: fixture imageとrequest logを初期化する]
    #   処理: [BytesIOへPNGを書き, request historyを空にする]
    #   引数: [self: fake opener]
    #   戻り値: []
    # }
    def __init__(self):
        stream = BytesIO()
        Image.new("RGB", (20, 10), "blue").save(stream, format="PNG")
        self.image_bytes = stream.getvalue()
        self.requests: list[tuple[str, str, object]] = []

    # {
    #   責務: [open: URL/HTTP methodに応じたfixture responseを返す]
    #   処理: [interrogator一覧, Civitai画像, Tagger応答を記録して返す]
    #   引数: [self: fake opener, request: urllib Request, timeout: request timeout]
    #   戻り値: [_FakeResponse: response body]
    # }
    def open(self, request, timeout):
        url = request.full_url
        method = request.get_method()
        body = request.data
        self.requests.append((method, url, body))
        if url.endswith("/interrogators"):
            return _FakeResponse(b'{"models":["fixture-model"]}', "application/json")
        if url.startswith("https://image.civitai.com/"):
            return _FakeResponse(self.image_bytes, "image/png")
        return _FakeResponse(
            b'{"tags":{"general":{"blue_hair":0.9,"shirt":0.8},"character":{"hero":0.95}}}',
            "application/json",
        )


# {
#   責務: [CivitaiPreviewTaggerTest: preview解析のloopback制限, tag分類入力, provenanceを検証する]
#   フィールド: [unittest assertion機能]
#   処理: [HTTP fixturesを注入し, 画像取得とTagger送信にネットワークを使わず確認する]
# }
class CivitaiPreviewTaggerTest(unittest.TestCase):
    """Verify Civitai images are transiently tagged only through loopback APIs."""

    # {
    #   責務: [_metadata: 画像previewを持つCivitai version fixtureを作る]
    #   処理: [固定LoRA候補と指定数のCivitai image referenceを組み合わせる]
    #   引数: [image_count: 生成する画像参照数]
    #   戻り値: [CivitaiLoraVersionMetadata: テスト用version metadata]
    # }
    @staticmethod
    def _metadata(image_count: int) -> CivitaiLoraVersionMetadata:
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
        return CivitaiLoraVersionMetadata(
            candidate,
            (),
            "Published",
            "Public",
            preview_images=tuple(
                CivitaiPreviewImage(
                    image_id=index + 1,
                    url=f"https://image.civitai.com/example/{index}.png",
                    nsfw_level=1,
                )
                for index in range(image_count)
            ),
        )

    # {
    #   責務: [test_preview_tags_are_classified_and_provenance_is_unknown: bounded image taggingとprovenanceを検証する]
    #   処理: [9参照中8枚だけがTaggerに送られ, source rightsはunknownのままでtagger情報が保持される]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_preview_tags_are_classified_and_provenance_is_unknown(self) -> None:
        opener = _FakeOpener()
        settings = TaggerSettings(
            "http://127.0.0.1:7861/pixai/v1/interrogate",
            "fixture-model",
        )
        with patch.object(civitai_preview_tagger, "_open_direct", return_value=opener):
            assets = civitai_preview_tagger.tag_civitai_preview_images(self._metadata(9), settings)

        self.assertEqual(len(assets), 8)
        self.assertEqual(assets[0].tags, ("blue_hair", "shirt", "hero"))
        self.assertIsNone(assets[0].image_file)
        self.assertEqual(assets[0].license_status, "unknown")
        self.assertEqual(assets[0].training_permission, "unknown")
        self.assertIn(("tagger_model", "fixture-model"), assets[0].source_metadata)
        self.assertIn(("tagger_backend", "pixai_http"), assets[0].source_metadata)
        self.assertIn(("preview_image_id", "1"), assets[0].source_metadata)
        self.assertEqual(
            sum(url.startswith("https://image.civitai.com/") for _, url, _ in opener.requests), 8
        )
        self.assertEqual(sum(method == "POST" for method, _, _ in opener.requests), 8)
        self.assertEqual(opener.requests[0][1], "http://127.0.0.1:7861/pixai/v1/interrogators")

    # {
    #   責務: [test_non_loopback_tagger_is_rejected_before_network: loopback外Taggerへの画像送信を拒否する]
    #   処理: [public host endpointを指定するとopenerを生成する前にValueErrorとなる]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_non_loopback_tagger_is_rejected_before_network(self) -> None:
        settings = TaggerSettings("https://example.invalid/pixai/v1/interrogate", "model")
        with patch.object(civitai_preview_tagger, "_open_direct") as open_direct:
            with self.assertRaisesRegex(ValueError, "loopback"):
                civitai_preview_tagger.tag_civitai_preview_images(self._metadata(1), settings)
        open_direct.assert_not_called()

    # {
    #   責務: [test_malformed_tagger_settings_are_rejected_before_network: 不正なURLとmodel文字列を拒否する]
    #   処理: [不正なURL形式, 過長URL, 制御文字入りmodelをそれぞれ検証する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_malformed_tagger_settings_are_rejected_before_network(self) -> None:
        invalid_settings = (
            TaggerSettings("http://[invalid/pixai/v1/interrogate", "model"),
            TaggerSettings(f"http://127.0.0.1/{'x' * 2048}", "model"),
            TaggerSettings("http://127.0.0.1:7861/pixai/v1/interrogate", "bad\nmodel"),
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings):
                with patch.object(civitai_preview_tagger, "_open_direct") as open_direct:
                    with self.assertRaises(ValueError):
                        civitai_preview_tagger.tag_civitai_preview_images(
                            self._metadata(1), settings
                        )
                open_direct.assert_not_called()

    # {
    #   責務: [test_missing_preview_image_is_reported: 画像参照なしを明示する]
    #   処理: [previewなしmetadataからtagger処理できないことを確認する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_missing_preview_image_is_reported(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "プレビュー画像"):
            civitai_preview_tagger.tag_civitai_preview_images(
                self._metadata(0),
                TaggerSettings("http://127.0.0.1:7861/pixai/v1/interrogate", "model"),
            )


if __name__ == "__main__":
    unittest.main()
