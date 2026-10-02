import json
import tempfile
import unittest
from pathlib import Path

from tools.maintenance.sync_comfyui_model_links import (
    _create_directory_link,
    _read_link_target,
    repair,
)


class ComfyUiModelLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.temporary_directory.name)
        self.models_root = self.root / "user_data" / "input" / "models"
        self.checkpoints = self.models_root / "checkpoints"
        self.checkpoints.mkdir(parents=True)
        (self.checkpoints / "model.safetensors").write_text("test model", encoding="utf-8")
        self.lora = self.models_root / "Lora"
        self.lora.mkdir()
        self.comfy_models = self.root / "external" / "ComfyUI" / "models"
        self.comfy_models.mkdir(parents=True)
        self.config_path = self.root / "user_data" / "input" / "config" / "common" / "paths.json"
        self.config_path.parent.mkdir(parents=True)
        self.config_path.write_text(
            json.dumps(
                {
                    "sd_root": str(self.root),
                    "models_root": str(self.models_root),
                    "comfyui_dir": str(self.root / "external" / "ComfyUI"),
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _make_broken_legacy_link(self, name, legacy_name=None):
        legacy = self.root / "models" / (legacy_name or name)
        legacy.mkdir(parents=True)
        link = self.comfy_models / name
        _create_directory_link(link, legacy)
        legacy.rmdir()
        return link

    def test_dry_run_leaves_broken_link_unchanged(self):
        link = self._make_broken_legacy_link("checkpoints")
        original_target = _read_link_target(link)

        plan = repair(self.config_path)

        self.assertEqual(len(plan.repairs), 1)
        self.assertEqual(_read_link_target(link), original_target)
        self.assertFalse(original_target.exists())

    def test_apply_retargets_only_to_existing_shared_models(self):
        checkpoint_link = self._make_broken_legacy_link("checkpoints")
        lora_link = self._make_broken_legacy_link("loras", "Lora")
        outsider = self.root / "third_party" / "missing"
        outsider.parent.mkdir()
        unrelated_link = self.comfy_models / "unrelated"
        _create_directory_link(unrelated_link, outsider)

        plan = repair(self.config_path, apply=True)

        self.assertEqual(len(plan.repairs), 2)
        self.assertEqual(_read_link_target(checkpoint_link), self.checkpoints.resolve())
        self.assertEqual(_read_link_target(lora_link), self.lora.resolve())
        self.assertEqual((checkpoint_link / "model.safetensors").read_text(encoding="utf-8"), "test model")
        self.assertEqual(_read_link_target(unrelated_link), outsider.resolve())
        self.assertFalse(outsider.exists())

    def test_valid_links_are_not_replaced(self):
        valid_link = self.comfy_models / "checkpoints"
        _create_directory_link(valid_link, self.checkpoints)

        plan = repair(self.config_path, apply=True)

        self.assertFalse(plan.repairs)
        self.assertEqual(_read_link_target(valid_link), self.checkpoints.resolve())


if __name__ == "__main__":
    unittest.main()
