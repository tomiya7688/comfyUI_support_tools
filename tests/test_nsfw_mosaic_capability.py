"""Tests for capability-based NudeNet mosaic selection."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.backend.a1111_image_generation_backend import A1111ImageGenerationBackend
from scripts.backend.comfyui_image_generation_backend import ComfyUIImageGenerationBackend
from scripts.backend.embedded_random_image import EmbeddedRandomImage
from scripts.backend.generation_capabilities import GenerationCapabilities
from scripts.tabs.random_image import RandomImageTab


# {
#   責務: [NsfwMosaicCapabilityTests: NudeNetモザイクがbackend capabilityで選ばれることを検証する]
#   フィールド: []
#   処理: [A1111だけが機能を宣言し, 非対応backendではAPIを呼ばず元画像を返すことを確認する]
# }
class NsfwMosaicCapabilityTests(unittest.TestCase):
    # {
    #   責務: [test_mosaic_controls_follow_backend_capability: モザイクUIがNudeNet capabilityに追従することを検証する]
    #   処理: [非対応時はUIを作らず, 対応時はbackend名に依存しない設定groupを作る]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_mosaic_controls_follow_backend_capability(self):
        unsupported = SimpleNamespace(
            backend_capabilities=GenerationCapabilities(frozenset()),
            var_enable_nsfw_mosaic=object(),
            var_nsfw_mosaic_factor=object(),
        )
        with patch("scripts.tabs.random_image.ttk.LabelFrame") as label_frame:
            RandomImageTab._build_nsfw_mosaic_controls(unsupported)
        label_frame.assert_not_called()

        mosaic = Mock()
        supported = SimpleNamespace(
            backend_capabilities=GenerationCapabilities(frozenset({"nudenet_mosaic"})),
            var_enable_nsfw_mosaic=object(),
            var_nsfw_mosaic_factor=object(),
        )
        with (
            patch("scripts.tabs.random_image.ttk.LabelFrame", return_value=mosaic) as label_frame,
            patch("scripts.tabs.random_image.ttk.Checkbutton"),
            patch("scripts.tabs.random_image.ttk.Label"),
            patch("scripts.tabs.random_image.ttk.Spinbox"),
        ):
            RandomImageTab._build_nsfw_mosaic_controls(supported)

        self.assertEqual(label_frame.call_args.kwargs["text"], "NSFWモザイク")
        self.assertNotIn("WebUI1111", label_frame.call_args.kwargs["text"])
        mosaic.pack.assert_called_once_with(fill="x", pady=6)

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
