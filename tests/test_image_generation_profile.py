"""Tests for backend-specific Random Image defaults."""

import unittest
from pathlib import Path

from scripts.backend.image_generation_profile import create_image_generation_profile


# {
#   責務: [ImageGenerationProfileTests: A1111とComfyUIのRandom Image既定値を検証する]
#   フィールド: []
#   処理: [API URL・保存先・checkpointがbackendごとの既存仕様と一致することを確認する]
# }
class ImageGenerationProfileTests(unittest.TestCase):
    # {
    #   責務: [test_comfyui_defaults_use_configured_api_and_output_folder: ComfyUIの既定値を検証する]
    #   処理: [1: ComfyUI profileを作成する, 2: API URL・保存先・checkpointを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_comfyui_defaults_use_configured_api_and_output_folder(self):
        profile = create_image_generation_profile(
            "comfyui",
            "http://127.0.0.1:7860",
            "http://localhost:8188/",
            Path("external/A1111"),
            Path("external/ComfyUI"),
            "20261010",
        )
        self.assertEqual(profile.api_url, "http://localhost:8188")
        self.assertEqual(profile.output_dir, Path("external/ComfyUI/output/KadokaTools/20261010"))
        self.assertEqual(profile.default_checkpoint, "shiitakeMix_v20.safetensors")

    # {
    #   責務: [test_a1111_defaults_accept_base_or_api_url: A1111の既定値とURL形式を検証する]
    #   処理: [1: base URL・endpoint URL各形式からprofileを作成する, 2: URL・保存先・checkpointを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_a1111_defaults_accept_base_or_api_url(self):
        for configured_url in ("http://localhost:7860", "http://localhost:7860/sdapi/v1"):
            with self.subTest(configured_url=configured_url):
                profile = create_image_generation_profile(
                    "a1111",
                    configured_url,
                    "http://127.0.0.1:8188",
                    Path("external/A1111"),
                    Path("external/ComfyUI"),
                    "20261010",
                )
                self.assertEqual(profile.api_url, "http://localhost:7860/sdapi/v1/txt2img")
                self.assertEqual(
                    profile.output_dir, Path("external/A1111/outputs/txt2img-images/20261010")
                )
                self.assertEqual(profile.default_checkpoint, "rinIllusionRNSFW_v30")

    # {
    #   責務: [test_unknown_backend_is_rejected: 未対応backendを拒否する]
    #   処理: [factoryに未知backendを渡してValueErrorを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_unknown_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            create_image_generation_profile(
                "unknown", "", "", Path("a1111"), Path("runtime"), "today"
            )


if __name__ == "__main__":
    unittest.main()
