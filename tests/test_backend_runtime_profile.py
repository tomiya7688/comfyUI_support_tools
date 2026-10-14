"""Tests for generation backend runtime selection defaults."""

import unittest
from pathlib import Path

from scripts.backend.backend_runtime_profile import create_backend_runtime_profile


# {
#   責務: [BackendRuntimeProfileTests: backend runtime selection profileを検証する]
#   フィールド: []
#   処理: [A1111・ComfyUI・不明backend・runtime overrideの選択結果を確認する]
# }
class BackendRuntimeProfileTests(unittest.TestCase):
    # {
    #   責務: [test_profile_selects_backend_defaults: backendごとのruntime既定値を確認する]
    #   処理: [1: A1111とComfyUIのprofileを作成する, 2: ID・表示名・runtime pathを比較する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_profile_selects_backend_defaults(self):
        cases = (
            ("a1111", "WebUI1111", Path("external/A1111")),
            ("comfyui", "ComfyUI", Path("external/ComfyUI")),
        )
        for backend, display_name, runtime_directory in cases:
            with self.subTest(backend=backend):
                profile = create_backend_runtime_profile(
                    backend,
                    Path("external/A1111"),
                    Path("external/ComfyUI"),
                )
                self.assertEqual(profile.backend, backend)
                self.assertEqual(profile.display_name, display_name)
                self.assertEqual(profile.runtime_directory, runtime_directory.resolve())

    # {
    #   責務: [test_profile_preserves_fallback_and_runtime_override: 従来fallbackとruntime overrideを確認する]
    #   処理: [1: 不明backendとoverride指定でprofileを作る, 2: A1111 fallbackとoverride pathを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_profile_preserves_fallback_and_runtime_override(self):
        profile = create_backend_runtime_profile(
            "unexpected",
            Path("external/A1111"),
            Path("external/ComfyUI"),
            Path("custom/runtime"),
        )
        self.assertEqual(profile.backend, "a1111")
        self.assertEqual(profile.display_name, "WebUI1111")
        self.assertEqual(profile.runtime_directory, Path("custom/runtime").resolve())

    # {
    #   責務: [test_profile_can_reject_unknown_backend: strict modeが未知backendを拒否することを検証する]
    #   処理: [fallback_backendを無効にしてprofile factoryがValueErrorを返すことを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_profile_can_reject_unknown_backend(self):
        with self.assertRaises(ValueError):
            create_backend_runtime_profile(
                "unexpected",
                Path("external/A1111"),
                Path("external/ComfyUI"),
                fallback_backend=None,
            )


if __name__ == "__main__":
    unittest.main()
