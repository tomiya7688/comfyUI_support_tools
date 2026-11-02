import json
import tempfile
import unittest
from pathlib import Path

from tools.maintenance.sync_comfyui_model_links import (
    _create_directory_link,
    _read_link_target,
    repair,
)


# {
#   責務: [ComfyUiModelLinkTests: related test fixtures and cases for ComfyUiModelLink behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     temporary_directory: temporary-directory owner for test files,
#     root: fixture root or application root under test,
#     models_root: shared model directory in the fixture tree,
#     checkpoints: checkpoint directory in the model fixture,
#     lora: LoRA model directory in the shared-model fixture,
#     comfy_models: ComfyUI model-link destination in the fixture,
#     config_path: temporary paths.json fixture,
#   ],
#   引数: []
# }
class ComfyUiModelLinkTests(unittest.TestCase):
    # {
    #   責務: [setUp: initializes per-test fixture state for ComfyUiModelLinkTests]
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

    # {
    #   責務: [tearDown: releases per-test resources created by ComfyUiModelLinkTests]
    #   処理: [1: stop owned workers/servers and release temporary files or UI resources]
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def tearDown(self):
        self.temporary_directory.cleanup()

    # {
    #   責務: [
    #     _make_broken_legacy_link: creates the legacy target and link, then removes the target to model a broken link,
    #   ],
    #   処理: [
    #     1: create a legacy model folder and directory link,
    #     2: remove the target folder while preserving the link,
    #   ],
    #   引数: [
    #     name: fixture item name (unspecified),
    #     legacy_name: name assigned to the removed legacy target (unspecified),
    #   ],
    #   戻り値: [result: link value built or selected by this helper]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def _make_broken_legacy_link(self, name, legacy_name=None):
        legacy = self.root / "models" / (legacy_name or name)
        legacy.mkdir(parents=True)
        link = self.comfy_models / name
        _create_directory_link(link, legacy)
        legacy.rmdir()
        return link

    # {
    #   責務: [
    #     test_dry_run_leaves_broken_link_unchanged: verifies the behavior described by "dry run leaves broken link unchanged",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for dry run leaves broken link unchanged,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_dry_run_leaves_broken_link_unchanged(self):
        link = self._make_broken_legacy_link("checkpoints")
        original_target = _read_link_target(link)

        plan = repair(self.config_path)

        self.assertEqual(len(plan.repairs), 1)
        self.assertEqual(_read_link_target(link), original_target)
        self.assertFalse(original_target.exists())

    # {
    #   責務: [
    #     test_apply_retargets_only_to_existing_shared_models: verifies the behavior described by "apply retargets only to existing shared models",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for apply retargets only to existing shared models,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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

    # {
    #   責務: [test_valid_links_are_not_replaced: verifies the behavior described by "valid links are not replaced"]
    #   処理: [
    #     1: arrange case data and fixture state for valid links are not replaced,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_valid_links_are_not_replaced(self):
        valid_link = self.comfy_models / "checkpoints"
        _create_directory_link(valid_link, self.checkpoints)

        plan = repair(self.config_path, apply=True)

        self.assertFalse(plan.repairs)
        self.assertEqual(_read_link_target(valid_link), self.checkpoints.resolve())


if __name__ == "__main__":
    unittest.main()
