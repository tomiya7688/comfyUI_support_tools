from __future__ import annotations

import unittest

from scripts.backend.model_choice_classification import classify_base_model_choice
from src.comfyui_support_tools.shared.model_identity import ModelFamily, ModelKind


# {
#   責務: [ModelChoiceClassificationTests: related test fixtures and cases for ModelChoiceClassification behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class ModelChoiceClassificationTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_classifies_checkpoint_from_catalog_kind_and_path_family: verifies the behavior described by "classifies checkpoint from catalog kind and path family",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for classifies checkpoint from catalog kind and path family,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_classifies_checkpoint_from_catalog_kind_and_path_family(self):
        result = classify_base_model_choice(
            "sdxl/base.safetensors",
            {"checkpoints": ["sdxl/base.safetensors"], "unets": []},
        )

        self.assertEqual(result.family, ModelFamily.SDXL)
        self.assertEqual(result.kind, ModelKind.CHECKPOINT)
        self.assertIn("declared model kind checkpoint", result.kind_reason)

    # {
    #   責務: [
    #     test_classifies_unet_from_catalog_kind: verifies the behavior described by "classifies unet from catalog kind",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for classifies unet from catalog kind,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_classifies_unet_from_catalog_kind(self):
        result = classify_base_model_choice(
            "flux/dev.safetensors",
            {"checkpoints": [], "unets": ["flux/dev.safetensors"]},
        )

        self.assertEqual(result.family, ModelFamily.FLUX)
        self.assertEqual(result.kind, ModelKind.UNET)

    # {
    #   責務: [
    #     test_conflicting_catalog_membership_keeps_kind_unknown: verifies the behavior described by "conflicting catalog membership keeps kind unknown",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for conflicting catalog membership keeps kind unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_conflicting_catalog_membership_keeps_kind_unknown(self):
        result = classify_base_model_choice(
            "sdxl/shared.safetensors",
            {"checkpoints": ["sdxl/shared.safetensors"], "unets": ["sdxl/shared.safetensors"]},
        )

        self.assertEqual(result.family, ModelFamily.SDXL)
        self.assertEqual(result.kind, ModelKind.UNKNOWN)
        self.assertIn("ambiguous", result.kind_reason)

    # {
    #   責務: [test_unknown_family_remains_unknown: verifies the behavior described by "unknown family remains unknown"]
    #   処理: [
    #     1: arrange case data and fixture state for unknown family remains unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_unknown_family_remains_unknown(self):
        result = classify_base_model_choice(
            "base.safetensors",
            {"checkpoints": ["base.safetensors"], "unets": []},
        )

        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertEqual(result.kind, ModelKind.CHECKPOINT)


if __name__ == "__main__":
    unittest.main()
