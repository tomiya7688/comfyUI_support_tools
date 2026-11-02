from __future__ import annotations

import unittest

from scripts.backend.prompt_lora_compatibility import (
    assess_prompt_loras,
    extract_lora_references,
    validate_prompt_loras,
)
from src.comfyui_support_tools.shared.model_compatibility import CompatibilityStatus


# {
#   責務: [PromptLoraCompatibilityTests: related test fixtures and cases for PromptLoraCompatibility behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class PromptLoraCompatibilityTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_extracts_unique_lora_names_in_prompt_order: verifies the behavior described by "extracts unique lora names in prompt order",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for extracts unique lora names in prompt order,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_extracts_unique_lora_names_in_prompt_order(self):
        self.assertEqual(
            extract_lora_references("<lora:sdxl/style:0.8>, <LoRA:sdxl/style:0.4> <lora:char:1>"),
            ["sdxl/style", "char"],
        )

    # {
    #   責務: [
    #     test_detects_definite_family_mismatch: verifies the behavior described by "detects definite family mismatch",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for detects definite family mismatch,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_detects_definite_family_mismatch(self):
        findings = assess_prompt_loras(
            "portrait, <lora:flux/detail:0.8>",
            "sdxl/base.safetensors",
            {
                "checkpoints": ["sdxl/base.safetensors"],
                "unets": [],
                "loras": ["flux/detail.safetensors"],
            },
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].result.status, CompatibilityStatus.INCOMPATIBLE)
        self.assertIn("does not match", findings[0].result.reason)

    # {
    #   責務: [
    #     test_unique_basename_is_resolved_and_family_match_is_compatible: verifies the behavior described by "unique basename is resolved and family match is compatible",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for unique basename is resolved and family match is compatible,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_unique_basename_is_resolved_and_family_match_is_compatible(self):
        findings = assess_prompt_loras(
            "<lora:style:0.7>",
            "sdxl/base.safetensors",
            {
                "checkpoints": ["sdxl/base.safetensors"],
                "unets": [],
                "loras": ["sdxl/style.safetensors"],
            },
        )

        self.assertEqual(findings[0].resolved_name, "sdxl/style.safetensors")
        self.assertEqual(findings[0].result.status, CompatibilityStatus.COMPATIBLE)
        self.assertIn("family-level", findings[0].result.reason)

    # {
    #   責務: [
    #     test_workflow_override_keeps_base_family_unknown: verifies the behavior described by "workflow override keeps base family unknown",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for workflow override keeps base family unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_workflow_override_keeps_base_family_unknown(self):
        findings = assess_prompt_loras(
            "<lora:sdxl/style:0.7>",
            None,
            {"checkpoints": [], "unets": [], "loras": ["sdxl/style.safetensors"]},
            base_model_reason="Workflow loader selection is ambiguous.",
        )

        self.assertEqual(findings[0].result.status, CompatibilityStatus.UNKNOWN)
        self.assertIn("Workflow loader selection is ambiguous.", findings[0].result.reason)

    # {
    #   責務: [
    #     test_missing_or_ambiguous_catalog_matches_remain_unknown: verifies the behavior described by "missing or ambiguous catalog matches remain unknown",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for missing or ambiguous catalog matches remain unknown,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_missing_or_ambiguous_catalog_matches_remain_unknown(self):
        choices = {
            "checkpoints": ["sdxl/base.safetensors"],
            "unets": [],
            "loras": ["sdxl/style.safetensors", "flux/style.safetensors"],
        }
        findings = assess_prompt_loras(
            "<lora:style:1>, <lora:not-installed:1>",
            "sdxl/base.safetensors",
            choices,
        )

        self.assertEqual([item.result.status for item in findings], [
            CompatibilityStatus.UNKNOWN,
            CompatibilityStatus.UNKNOWN,
        ])
        self.assertIn("ambiguous", findings[0].result.reason)
        self.assertIn("No matching", findings[1].result.reason)

    # {
    #   責務: [
    #     test_incompatible_lora_prevents_generation_but_unknown_only_warns: verifies the behavior described by "incompatible lora prevents generation but unknown only warns",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for incompatible lora prevents generation but unknown only warns,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_incompatible_lora_prevents_generation_but_unknown_only_warns(self):
        choices = {
            "checkpoints": ["sdxl/base.safetensors"],
            "unets": [],
            "loras": ["flux/detail.safetensors"],
        }
        logs = []
        with self.assertRaisesRegex(ValueError, "生成を中止"):
            validate_prompt_loras(
                "<lora:flux/detail:1>", "sdxl/base.safetensors", choices, logs.append
            )
        self.assertIn("[incompatible]", logs[0])

        unknown_logs = []
        findings = validate_prompt_loras(
            "<lora:missing:1>", "sdxl/base.safetensors", choices, unknown_logs.append
        )
        self.assertEqual(findings[0].result.status, CompatibilityStatus.UNKNOWN)
        self.assertIn("[unknown]", unknown_logs[0])


if __name__ == "__main__":
    unittest.main()
