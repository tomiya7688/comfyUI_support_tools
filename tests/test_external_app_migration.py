import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.maintenance.move_external_apps import MigrationError, migrate


# {
#   責務: [ExternalAppMigrationTests: related test fixtures and cases for ExternalAppMigration behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     temporary_directory: temporary-directory owner for test files,
#     root: fixture root or application root under test,
#     source: source application directory in the migration fixture,
#     config_path: temporary paths.json fixture,
#     config: configuration mapping loaded by the fixture,
#   ],
#   引数: []
# }
class ExternalAppMigrationTests(unittest.TestCase):
    # {
    #   責務: [setUp: initializes per-test fixture state for ExternalAppMigrationTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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

    # {
    #   責務: [tearDown: releases per-test resources created by ExternalAppMigrationTests]
    #   処理: [1: stop owned workers/servers and release temporary files or UI resources]
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def tearDown(self):
        self.temporary_directory.cleanup()

    # {
    #   責務: [
    #     test_dry_run_does_not_move_or_rewrite: verifies the behavior described by "dry run does not move or rewrite",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for dry run does not move or rewrite,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_dry_run_does_not_move_or_rewrite(self):
        before = self.config_path.read_text(encoding="utf-8")

        migrate(self.root)

        self.assertTrue(self.source.exists())
        self.assertFalse((self.root / "external" / "ComfyUI").exists())
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), before)

    # {
    #   責務: [
    #     test_dry_run_log_supports_legacy_console_encoding: verifies the behavior described by "dry run log supports legacy console encoding",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for dry run log supports legacy console encoding,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: super().write built or selected by this helper]
    # }
    def test_dry_run_log_supports_legacy_console_encoding(self):
        # {
        #   責務: [Cp1252Console: text stream test double that emulates a legacy Windows console encoding]
        #   処理: [1: provide the configured fields and methods used by the surrounding cases]
        #   フィールド: [encoding: encoding fixture state used by the test cases]
        #   引数: []
        # }
        class Cp1252Console(io.StringIO):
            encoding = "cp1252"

            # {
            #   責務: [write: writes the configured fixture text through the wrapped stream]
            #   処理: [
            #     1: encode the text using the emulated console encoding,
            #     2: forward encoded text to the wrapped stream,
            #   ],
            #   引数: [value: value to serialize or write (unspecified)]
            #   戻り値: [result: super().write built or selected by this helper]
            # }
            def write(self, value):
                value.encode(self.encoding)
                return super().write(value)

        console = Cp1252Console()
        with patch("sys.stdout", console):
            migrate(self.root)

        self.assertIn("\\u5916", console.getvalue())

    # {
    #   責務: [
    #     test_collision_stops_before_any_move: verifies the behavior described by "collision stops before any move",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for collision stops before any move,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_collision_stops_before_any_move(self):
        destination = self.root / "external" / "ComfyUI"
        destination.mkdir(parents=True)

        with self.assertRaises(MigrationError):
            migrate(self.root, apply=True)

        self.assertTrue(self.source.exists())
        self.assertTrue(destination.exists())

    # {
    #   責務: [
    #     test_apply_moves_folder_and_preserves_unknown_config: verifies the behavior described by "apply moves folder and preserves unknown config",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for apply moves folder and preserves unknown config,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_apply_moves_folder_and_preserves_unknown_config(self):
        migrate(self.root, apply=True)

        destination = self.root / "external" / "ComfyUI"
        updated = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertFalse(self.source.exists())
        self.assertEqual((destination / "keep.txt").read_text(encoding="utf-8"), "external app")
        self.assertEqual(Path(updated["comfyui_dir"]), destination)
        self.assertEqual(updated["unknown_setting"], {"keep": True})

    # {
    #   責務: [
    #     test_models_and_output_stay_at_original_paths: verifies the behavior described by "models and output stay at original paths",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for models and output stay at original paths,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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
