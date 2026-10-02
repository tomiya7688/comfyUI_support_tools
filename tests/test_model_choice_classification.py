from __future__ import annotations

import unittest

from scripts.backend.model_choice_classification import classify_base_model_choice
from src.comfyui_support_tools.shared.model_identity import ModelFamily, ModelKind


class ModelChoiceClassificationTests(unittest.TestCase):
    def test_classifies_checkpoint_from_catalog_kind_and_path_family(self):
        result = classify_base_model_choice(
            "sdxl/base.safetensors",
            {"checkpoints": ["sdxl/base.safetensors"], "unets": []},
        )

        self.assertEqual(result.family, ModelFamily.SDXL)
        self.assertEqual(result.kind, ModelKind.CHECKPOINT)
        self.assertIn("declared model kind checkpoint", result.kind_reason)

    def test_classifies_unet_from_catalog_kind(self):
        result = classify_base_model_choice(
            "flux/dev.safetensors",
            {"checkpoints": [], "unets": ["flux/dev.safetensors"]},
        )

        self.assertEqual(result.family, ModelFamily.FLUX)
        self.assertEqual(result.kind, ModelKind.UNET)

    def test_conflicting_catalog_membership_keeps_kind_unknown(self):
        result = classify_base_model_choice(
            "sdxl/shared.safetensors",
            {"checkpoints": ["sdxl/shared.safetensors"], "unets": ["sdxl/shared.safetensors"]},
        )

        self.assertEqual(result.family, ModelFamily.SDXL)
        self.assertEqual(result.kind, ModelKind.UNKNOWN)
        self.assertIn("ambiguous", result.kind_reason)

    def test_unknown_family_remains_unknown(self):
        result = classify_base_model_choice(
            "base.safetensors",
            {"checkpoints": ["base.safetensors"], "unets": []},
        )

        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertEqual(result.kind, ModelKind.CHECKPOINT)


if __name__ == "__main__":
    unittest.main()
