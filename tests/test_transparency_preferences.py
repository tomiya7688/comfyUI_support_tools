import json
import os
import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.shared.transparency_preferences import TransparencyPreferenceStore


# {
# 責務: [ TransparencyPreferenceStoreTests: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class TransparencyPreferenceStoreTests(unittest.TestCase):
    # {
    # 責務: [ test_default_is_off_and_explicit_global_choice_persists: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_default_is_off_and_explicit_global_choice_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TransparencyPreferenceStore(Path(directory) / "prefs.json")
            self.assertFalse(store.global_enabled())
            store.set_global_enabled(True)
            self.assertTrue(store.global_enabled())
            payload = json.loads(store.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], 1)

    # {
    # 責務: [ test_application_override_is_optional_and_secret_free: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_application_override_is_optional_and_secret_free(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TransparencyPreferenceStore(Path(directory) / "prefs.json")
            self.assertIsNone(store.application_override("generation"))
            store.set_global_enabled(True)
            store.set_application_override("generation", False)
            self.assertFalse(store.application_override("generation"))
            self.assertTrue(store.global_enabled())
            store.set_application_override("generation", None)
            self.assertIsNone(store.application_override("generation"))
            self.assertNotIn("key", store.path.read_text(encoding="utf-8").lower())

    # {
    # 責務: [ test_malformed_config_and_symlink_are_rejected: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_malformed_config_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prefs.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "schema"):
                TransparencyPreferenceStore(path).global_enabled()
            if hasattr(os, "symlink"):
                target = Path(directory) / "target.json"
                target.write_text(
                    '{"schema_version":1,"global_enabled":false,"application_overrides":{}}'
                )
                link = Path(directory) / "link.json"
                try:
                    link.symlink_to(target)
                except OSError:
                    return
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    TransparencyPreferenceStore(link).global_enabled()


if __name__ == "__main__":
    unittest.main()
