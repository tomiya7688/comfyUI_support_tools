import json
import tempfile
import unittest
from pathlib import Path

from tools.maintenance.move_external_apps import MigrationError, migrate


class ExternalAppMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "ComfyUI"
        self.source.mkdir()
        (self.source / "keep.txt").write_text("external app", encoding="utf-8")
        self.config_path = self.root / "user_data" / "input" / "config" / "common" / "paths.json"
        self.config_path.parent.mkdir(parents=True)
        self.config = {"comfyui_dir": str(self.source), "unknown_setting": {"keep": True}}
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_dry_run_does_not_move_or_rewrite(self):
        before = self.config_path.read_text(encoding="utf-8")

        migrate(self.root)

        self.assertTrue(self.source.exists())
        self.assertFalse((self.root / "external" / "ComfyUI").exists())
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), before)

    def test_collision_stops_before_any_move(self):
        destination = self.root / "external" / "ComfyUI"
        destination.mkdir(parents=True)

        with self.assertRaises(MigrationError):
            migrate(self.root, apply=True)

        self.assertTrue(self.source.exists())
        self.assertTrue(destination.exists())

    def test_apply_moves_folder_and_preserves_unknown_config(self):
        migrate(self.root, apply=True)

        destination = self.root / "external" / "ComfyUI"
        updated = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertFalse(self.source.exists())
        self.assertEqual((destination / "keep.txt").read_text(encoding="utf-8"), "external app")
        self.assertEqual(Path(updated["comfyui_dir"]), destination)
        self.assertEqual(updated["unknown_setting"], {"keep": True})

    def test_models_and_output_stay_at_original_paths(self):
        models = self.source / "models"
        output = self.source / "output"
        models.mkdir()
        output.mkdir()
        (models / "model.txt").write_text("model data", encoding="utf-8")
        (output / "image.txt").write_text("generated data", encoding="utf-8")

        migrate(self.root, apply=True)

        destination = self.root / "external" / "ComfyUI"
        self.assertEqual((models / "model.txt").read_text(encoding="utf-8"), "model data")
        self.assertEqual((output / "image.txt").read_text(encoding="utf-8"), "generated data")
        self.assertEqual((destination / "models" / "model.txt").read_text(encoding="utf-8"), "model data")
        self.assertEqual((destination / "output" / "image.txt").read_text(encoding="utf-8"), "generated data")


if __name__ == "__main__":
    unittest.main()
