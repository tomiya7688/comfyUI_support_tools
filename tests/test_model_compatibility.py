from __future__ import annotations

import unittest

from src.comfyui_support_tools.shared.model_compatibility import (
    CompatibilityStatus,
    check_lora_compatibility,
)
from src.comfyui_support_tools.shared.model_identity import classify_model


# {
#   責務: [LoraCompatibilityTests: related test fixtures and cases for LoraCompatibility behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class LoraCompatibilityTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_same_known_family_is_compatible: verifies the behavior described by "same known family is compatible",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for same known family is compatible,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_same_known_family_is_compatible(self):
        lora = classify_model("models/loras/sdxl/style.safetensors")
        base_model = classify_model("models/checkpoints/sdxl/base.safetensors")

        result = check_lora_compatibility(lora, base_model)

        self.assertEqual(result.status, CompatibilityStatus.COMPATIBLE)
        self.assertIn("family-level", result.reason)

    # {
    #   責務: [
    #     test_different_known_families_are_incompatible: verifies the behavior described by "different known families are incompatible",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for different known families are incompatible,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_different_known_families_are_incompatible(self):
        lora = classify_model("models/loras/sd15/style.safetensors")
        base_model = classify_model("models/unet/flux1-dev.safetensors")

        result = check_lora_compatibility(lora, base_model)

        self.assertEqual(result.status, CompatibilityStatus.INCOMPATIBLE)
        self.assertIn("sd1.5", result.reason)
        self.assertIn("flux", result.reason)

    # {
    #   責務: [test_unknown_family_stays_unknown: verifies the behavior described by "unknown family stays unknown"]
    #   処理: [
    #     1: arrange case data and fixture state for unknown family stays unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_unknown_family_stays_unknown(self):
        lora = classify_model("models/loras/unknown/style.safetensors")
        base_model = classify_model("models/checkpoints/sdxl/base.safetensors")

        result = check_lora_compatibility(lora, base_model)

        self.assertEqual(result.status, CompatibilityStatus.UNKNOWN)
        self.assertIn("No recognized family marker", result.reason)

    # {
    #   責務: [
    #     test_unknown_base_family_stays_unknown: verifies the behavior described by "unknown base family stays unknown",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for unknown base family stays unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_unknown_base_family_stays_unknown(self):
        lora = classify_model("models/loras/sdxl/style.safetensors")
        base_model = classify_model("models/checkpoints/base.safetensors")

        result = check_lora_compatibility(lora, base_model)

        self.assertEqual(result.status, CompatibilityStatus.UNKNOWN)

    # {
    #   責務: [
    #     test_wrong_adapter_kind_stays_unknown: verifies the behavior described by "wrong adapter kind stays unknown",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for wrong adapter kind stays unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_wrong_adapter_kind_stays_unknown(self):
        checkpoint = classify_model("models/checkpoints/sdxl/base.safetensors")
        base_model = classify_model("models/checkpoints/sdxl/other.safetensors")

        result = check_lora_compatibility(checkpoint, base_model)

        self.assertEqual(result.status, CompatibilityStatus.UNKNOWN)
        self.assertIn("not LoRA", result.reason)

    # {
    #   責務: [test_wrong_base_kind_stays_unknown: verifies the behavior described by "wrong base kind stays unknown"]
    #   処理: [
    #     1: arrange case data and fixture state for wrong base kind stays unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_wrong_base_kind_stays_unknown(self):
        lora = classify_model("models/loras/sdxl/style.safetensors")
        vae = classify_model("models/vae/sdxl/vae.safetensors")

        result = check_lora_compatibility(lora, vae)

        self.assertEqual(result.status, CompatibilityStatus.UNKNOWN)
        self.assertIn("expected checkpoint or UNet", result.reason)


if __name__ == "__main__":
    unittest.main()
