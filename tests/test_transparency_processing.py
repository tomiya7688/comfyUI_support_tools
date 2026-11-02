import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from comfyui_support_tools.shared.transparency_preferences import TransparencyPreferenceStore
from comfyui_support_tools.shared.transparency_processing import apply_generation_transparency


# {
# 責務: [ GenerationTransparencyTests: 状態と振る舞いをまとめる ]
# フィールド: [主要な状態: クラスが管理する状態]
# }
class GenerationTransparencyTests(unittest.TestCase):
    # {
    # 責務: [ setUp: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / "generated.png"
        Image.new("RGB", (80, 60), "blue").save(self.image)
        self.preferences = TransparencyPreferenceStore(self.root / "settings" / "transparency.json")

    # {
    # 責務: [ test_default_off_does_not_create_outputs: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_default_off_does_not_create_outputs(self):
        result = apply_generation_transparency(
            self.image,
            application_id="sequence.comfyui",
            backend="comfyui",
            prompt="private prompt",
            preferences=self.preferences,
        )
        self.assertFalse(result["transparency_enabled"])
        self.assertEqual(result["artifacts"], [])
        self.assertFalse(self.image.with_suffix(".png.transparency.json").exists())

    # {
    # 責務: [ test_opt_in_records_generation_without_prompt_disclosure: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_opt_in_records_generation_without_prompt_disclosure(self):
        original = self.image.read_bytes()
        result = apply_generation_transparency(
            self.image,
            application_id="sequence.comfyui",
            backend="comfyui",
            prompt="private prompt",
            model_id="private-model",
            workflow={"node": "private"},
            transparency_options={"enabled": True},
            preferences=self.preferences,
        )
        self.assertTrue(result["transparency_enabled"])
        payload = json.loads(Path(result["transparency_sidecar"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["generated_or_modified"], "generated")
        self.assertEqual(payload["disclosure"]["prompt"], {"level": "none"})
        self.assertEqual(payload["disclosure"]["model"], {"level": "none"})
        self.assertNotIn("private prompt", json.dumps(payload))
        self.assertNotIn("private-model", json.dumps(payload))
        self.assertNotIn("private", json.dumps(payload))
        self.assertEqual(self.image.read_bytes(), original)

    # {
    # 責務: [ test_png_metadata_copy_is_opt_in_and_verified: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_png_metadata_copy_is_opt_in_and_verified(self):
        result = apply_generation_transparency(
            self.image,
            application_id="sequence.comfyui",
            backend="comfyui",
            prompt="prompt",
            transparency_options={
                "enabled": True,
                "write_png_metadata": True,
                "write_sidecar": False,
            },
            preferences=self.preferences,
        )
        copy = Path(result["image"])
        self.assertEqual(copy.name, "generated.transparency.png")
        self.assertTrue(copy.is_file())
        self.assertEqual(result["artifacts"], [str(copy)])
        self.assertIsNone(result["transparency_sidecar"])

    # {
    # 責務: [ test_c2pa_signing_requires_secure_signer_injection: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_c2pa_signing_requires_secure_signer_injection(self):
        with self.assertRaisesRegex(ValueError, "injected secure signer provider"):
            apply_generation_transparency(
                self.image,
                application_id="sequence.comfyui",
                backend="comfyui",
                prompt="prompt",
                transparency_options={"enabled": True, "sign_c2pa": True},
                preferences=self.preferences,
            )

    # {
    # 責務: [ test_global_and_application_settings_can_be_overridden_per_generation: 入力を処理して結果を返す ]
    # 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
    # 引数: [self]
    # 戻り値: [処理結果]
    # }
    def test_global_and_application_settings_can_be_overridden_per_generation(self):
        self.preferences.set_global_enabled(True)
        self.preferences.set_application_override("sequence.comfyui", False)
        off = apply_generation_transparency(
            self.image,
            application_id="sequence.comfyui",
            backend="comfyui",
            prompt="prompt",
            preferences=self.preferences,
        )
        self.assertFalse(off["transparency_enabled"])
        on = apply_generation_transparency(
            self.image,
            application_id="sequence.comfyui",
            backend="comfyui",
            prompt="prompt",
            transparency_options={"enabled": True},
            preferences=self.preferences,
        )
        self.assertTrue(on["transparency_enabled"])


if __name__ == "__main__":
    unittest.main()
