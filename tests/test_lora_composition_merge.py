"""Focused numerical checks for static LoRA merge implementations."""

from __future__ import annotations

import unittest

import numpy as np

from comfyui_support_tools.shared.lora_composition.contracts import (
    LoRAAdapter,
    LoRARole,
    MergeMethod,
)
from comfyui_support_tools.shared.lora_composition.merge import merge_adapters


# {
# 責務: [LoRACompositionMergeTests: validate deterministic low-rank merge output]
# フィールド: [shared layer and compatible adapter fixtures]
# 処理: [check weighted update composition and output rank compression]
# }
class LoRACompositionMergeTests(unittest.TestCase):
    # {
    # 責務: [test_weighted_merge_composes_compatible_updates]
    # 処理: [merge subject and style updates into bounded A/B output factors]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_weighted_merge_composes_compatible_updates(self):
        layer = "lora_unet_block.attn.to_q"
        subject = LoRAAdapter(
            "subject",
            {
                f"{layer}.lora_A.weight": np.array([[1.0, 0.0]]),
                f"{layer}.lora_B.weight": np.array([[1.0], [0.0]]),
            },
            "sdxl",
            "SDXL",
            1,
            1.0,
            LoRARole.SUBJECT,
        )
        style = LoRAAdapter(
            "style",
            {
                f"{layer}.lora_A.weight": np.array([[0.0, 1.0]]),
                f"{layer}.lora_B.weight": np.array([[0.0], [1.0]]),
            },
            "sdxl",
            "SDXL",
            1,
            1.0,
            LoRARole.STYLE,
        )

        merged = merge_adapters(
            (subject, style),
            "sdxl/base",
            "SDXL",
            {"subject": 0.5, "style": 0.25},
            MergeMethod.WEIGHTED,
            rank_limit=1,
        )

        update = merged[f"{layer}.lora_B.weight"] @ merged[f"{layer}.lora_A.weight"]
        self.assertEqual(update.shape, (2, 2))
        self.assertLessEqual(merged[f"{layer}.lora_A.weight"].shape[0], 1)
        self.assertTrue(np.isfinite(update).all())
