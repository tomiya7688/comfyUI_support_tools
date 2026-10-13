"""Tests for backend-specific local launch settings."""

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import context
from scripts.backend.backend_launch_spec import create_backend_launch_spec


# {
#   責務: [BackendLaunchSpecTests: backendごとの起動設定を検証する]
#   フィールド: []
#   処理: [factoryが既存のA1111とComfyUI起動値を返し, 不正backendを拒否することを確認する]
# }
class BackendLaunchSpecTests(unittest.TestCase):
    # {
    #   責務: [test_context_resolves_configured_runtime_directory: contextがbackendごとのruntime配置を解決することを検証する]
    #   処理: [runtime directory設定をpatchし, A1111・ComfyUIの対応と未知backend拒否を確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_context_resolves_configured_runtime_directory(self):
        a1111_directory = Path("external/A1111")
        comfyui_directory = Path("external/ComfyUI")
        with (
            patch.object(context, "A1111_DIR", a1111_directory),
            patch.object(context, "COMFYUI_DIR", comfyui_directory),
        ):
            self.assertEqual(context.configured_backend_runtime_directory("a1111"), a1111_directory)
            self.assertEqual(context.configured_backend_runtime_directory("comfyui"), comfyui_directory)
            with self.assertRaises(ValueError):
                context.configured_backend_runtime_directory("unknown")

    # {
    #   責務: [test_comfyui_spec_keeps_low_vram_launch_defaults: ComfyUI既定設定を検証する]
    #   処理: [1: ComfyUI設定を作る, 2: script・API・port・flagsを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_comfyui_spec_keeps_low_vram_launch_defaults(self):
        spec = create_backend_launch_spec(
            "comfyui",
            "http://127.0.0.1:7860",
            "http://localhost:8188/",
            Path("models/checkpoints"),
            Path("models"),
        )
        self.assertEqual(spec.display_name, "ComfyUI")
        self.assertEqual(spec.launch_script_name, "main.py")
        self.assertEqual(spec.health_url, "http://localhost:8188/system_stats")
        self.assertEqual(spec.port, 8188)
        self.assertEqual(
            spec.default_flags,
            ("--listen", "127.0.0.1", "--port", "8188", "--lowvram", "--disable-auto-launch"),
        )

    # {
    #   責務: [test_a1111_spec_keeps_model_paths_and_normalizes_api_url: A1111既定設定を検証する]
    #   処理: [1: A1111設定を作る, 2: script・API・port・共有model pathを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_a1111_spec_keeps_model_paths_and_normalizes_api_url(self):
        spec = create_backend_launch_spec(
            "a1111",
            "http://localhost:7860/sdapi/v1",
            "http://127.0.0.1:8188",
            Path("models/checkpoints"),
            Path("models"),
        )
        self.assertEqual(spec.display_name, "WebUI1111")
        self.assertEqual(spec.launch_script_name, "launch.py")
        self.assertEqual(spec.health_url, "http://localhost:7860/sdapi/v1/progress")
        self.assertEqual(spec.port, 7860)
        self.assertIn(str(Path("models/checkpoints")), spec.default_flags)
        self.assertIn(str(Path("models/Lora")), spec.default_flags)
        self.assertIn("--lowvram", spec.default_flags)

    # {
    #   責務: [test_unknown_backend_is_rejected: 未対応backendの入力を拒否する]
    #   処理: [未知のbackendでfactoryを呼び出し, ValueErrorを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_unknown_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            create_backend_launch_spec("unknown", "", "", Path("checkpoints"), Path("models"))

    # {
    #   責務: [test_context_builds_launch_spec_for_selected_backend: contextが選択中backendの起動設定を作ることを検証する]
    #   処理: [1: A1111とComfyUIの実行時設定を切り替える, 2: 各backend固有のscriptとhealth URLを確認する]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_context_builds_launch_spec_for_selected_backend(self):
        with patch.object(context, "RUNTIME_BACKEND", "a1111"):
            a1111_spec = context.create_configured_backend_launch_spec()
        with patch.object(context, "RUNTIME_BACKEND", "comfyui"):
            comfyui_spec = context.create_configured_backend_launch_spec()

        self.assertEqual(a1111_spec.launch_script_name, "launch.py")
        self.assertEqual(a1111_spec.health_url, "http://127.0.0.1:7860/sdapi/v1/progress")
        self.assertEqual(comfyui_spec.launch_script_name, "main.py")
        self.assertEqual(comfyui_spec.health_url, "http://127.0.0.1:8188/system_stats")


if __name__ == "__main__":
    unittest.main()
