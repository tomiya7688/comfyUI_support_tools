"""Tests for Character Registry user-selected path persistence."""

import tempfile
import unittest
from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.ui.processing.character_registry_path_settings_store import (
    CharacterRegistryPathSettingsStore,
)


# {
#   責務: [CharacterRegistryPathSettingsStoreTest: user-selected path設定の読書と不正JSON処理を検証する]
#   フィールド: [unittest assertion機能]
#   処理: [一時directoryだけを使い, path設定の保存・再読込結果を確認する]
# }
class CharacterRegistryPathSettingsStoreTest(unittest.TestCase):
    # {
    #   責務: [test_missing_file_returns_empty_paths: 未作成設定の既定値を検証する]
    #   処理: [存在しないJSONをloadし, 二つのpathが空文字であることを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_missing_file_returns_empty_paths(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = CharacterRegistryPathSettingsStore(Path(directory) / "settings.json")

            self.assertEqual(
                store.load(),
                {"dataset_root": "", "profile_directory": ""},
            )

    # {
    #   責務: [test_paths_round_trip: path設定がJSONへ保存され再読込できることを検証する]
    #   処理: [二つのpathを保存して同じ値がloadされることを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_paths_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            settings_path = Path(directory) / "nested" / "settings.json"
            store = CharacterRegistryPathSettingsStore(settings_path)
            expected = {
                "dataset_root": str(Path(directory) / "dataset"),
                "profile_directory": str(Path(directory) / "profiles"),
            }

            store.save(**expected)

            self.assertEqual(store.load(), expected)

    # {
    #   責務: [test_invalid_setting_shape_is_rejected: 不正JSONと不正field型を拒否する]
    #   処理: [JSON arrayと数値fieldの二ケースでValueErrorを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_invalid_setting_shape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            settings_path = Path(directory) / "settings.json"
            store = CharacterRegistryPathSettingsStore(settings_path)
            for invalid_json in ("[]", '{"dataset_root": 12}'):
                settings_path.write_text(invalid_json, encoding="utf-8")
                with self.subTest(invalid_json=invalid_json):
                    with self.assertRaises(ValueError):
                        store.load()


if __name__ == "__main__":
    unittest.main()
