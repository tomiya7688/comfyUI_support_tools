from __future__ import annotations

import unittest

from src.comfyui_support_tools.shared.model_compatibility import (
    CompatibilityStatus,
    check_lora_compatibility,
)
from src.comfyui_support_tools.shared.model_identity import classify_model


class LoraCompatibilityTests(unittest.TestCase):
    def test_same_known_family_is_compatible(self):
        lora = classify_model("models/loras/sdxl/style.safetensors")
        base_model = classify_model("models/checkpoints/sdxl/base.safetensors")

        result = check_lora_compatibility(lora, base_model)

        self.assertEqual(result.status, CompatibilityStatus.COMPATIBLE)
        self.assertIn("family-level", result.reason)

    def test_different_known_families_are_incompatible(self):
        lora = classify_model("models/loras/sd15/style.safetensors")
        base_model = classify_model("models/unet/flux1-dev.safetensors")

        result = check_lora_compatibility(lora, base_model)

        self.assertEqual(result.status, CompatibilityStatus.INCOMPATIBLE)
        self.assertIn("sd1.5", result.reason)
        self.assertIn("flux", result.reason)

    def test_unknown_family_stays_unknown(self):
        lora = classify_model("models/loras/unknown/style.safetensors")
        base_model = classify_model("models/checkpoints/sdxl/base.safetensors")

        result = check_lora_compatibility(lora, base_model)

        self.assertEqual(result.status, CompatibilityStatus.UNKNOWN)
        self.assertIn("No recognized family marker", result.reason)

    def test_unknown_base_family_stays_unknown(self):
        lora = classify_model("models/loras/sdxl/style.safetensors")
        base_model = classify_model("models/checkpoints/base.safetensors")

        result = check_lora_compatibility(lora, base_model)

        self.assertEqual(result.status, CompatibilityStatus.UNKNOWN)

    def test_wrong_adapter_kind_stays_unknown(self):
        checkpoint = classify_model("models/checkpoints/sdxl/base.safetensors")
        base_model = classify_model("models/checkpoints/sdxl/other.safetensors")

        result = check_lora_compatibility(checkpoint, base_model)

        self.assertEqual(result.status, CompatibilityStatus.UNKNOWN)
        self.assertIn("not LoRA", result.reason)

    def test_wrong_base_kind_stays_unknown(self):
        lora = classify_model("models/loras/sdxl/style.safetensors")
        vae = classify_model("models/vae/sdxl/vae.safetensors")

        result = check_lora_compatibility(lora, vae)

        self.assertEqual(result.status, CompatibilityStatus.UNKNOWN)
        self.assertIn("expected checkpoint or UNet", result.reason)


if __name__ == "__main__":
    unittest.main()
