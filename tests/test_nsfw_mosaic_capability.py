"""Tests for capability-based NudeNet mosaic selection."""

import unittest
from unittest.mock import patch

from scripts.backend.a1111_image_generation_backend import A1111ImageGenerationBackend
from scripts.backend.comfyui_image_generation_backend import ComfyUIImageGenerationBackend
from scripts.backend.embedded_random_image import EmbeddedRandomImage


# {
#   責務: [NsfwMosaicCapabilityTests: NudeNetモザイクがbackend capabilityで選ばれることを検証する]
#   フィールド: []
#   処理: [A1111だけが機能を宣言し, 非対応backendではAPIを呼ばず元画像を返すことを確認する]
# }
class NsfwMosaicCapabilityTests(unittest.TestCase):
    # {
    #   責務: [test_a1111_declares_nudenet_mosaic_support: A1111のNudeNet capabilityを検証する]
    #   処理: [A1111 adapterを構築し, capabilityの宣言を確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_a1111_declares_nudenet_mosaic_support(self):
        backend = A1111ImageGenerationBackend(
            "http://localhost:7860/sdapi/v1/txt2img", 30, lambda *_args, **_kwargs: None
        )
        self.assertTrue(backend.capabilities.supports("nudenet_mosaic"))

    # {
    #   責務: [test_comfyui_keeps_original_image_without_nudenet_request: ComfyUIでは元画像を保持する]
    #   処理: [1: ComfyUI adapterでモザイクを要求する, 2: API呼び出しなしで元bytesが返ることを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_comfyui_keeps_original_image_without_nudenet_request(self):
        # {
        #   責務: [FakeClient: ComfyUI adapterの初期化に必要なnetwork-free stubを提供する]
        #   フィールド: []
        #   処理: []
        # }
        class FakeClient:
            # {
            #   責務: [__init__: stub clientを初期化する]
            #   処理: []
            #   引数: [self: stub instance, _url: 未使用のAPI URL, _timeout: 未使用timeout]
            #   戻り値: []
            # }
            def __init__(self, _url, _timeout):
                pass

        backend = ComfyUIImageGenerationBackend("http://localhost:8188", 30, FakeClient)
        generator = EmbeddedRandomImage()
        generator.enable_nsfw_mosaic = True
        messages = []
        generator._log = messages.append
        image_bytes = b"original-image"

        with patch("scripts.backend.embedded_random_image.requests.post") as post:
            result = generator._apply_nsfw_mosaic(image_bytes, backend)

        self.assertFalse(backend.capabilities.supports("nudenet_mosaic"))
        self.assertEqual(result, image_bytes)
        post.assert_not_called()
        self.assertTrue(any("対応していない" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
