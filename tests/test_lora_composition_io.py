"""Focused checks for portable LoRA composition recipe persistence."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.shared.lora_composition.contracts import (
    EvaluationCase,
    LoRAComposition,
    MergeMethod,
)
from comfyui_support_tools.shared.lora_composition.io import save_composition


# {
# 責務: [LoRACompositionIOTests: verify portable composition recipes survive JSON export]
# フィールド: [temporary output directory]
# 処理: [check method, scales, fixed-seed prompts and provenance are persisted]
# }
class LoRACompositionIOTests(unittest.TestCase):
    # {
    # 責務: [test_recipe_export_preserves_scales_cases_and_provenance]
    # 処理: [write a recipe and inspect its portable schema fields]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_recipe_export_preserves_scales_cases_and_provenance(self):
        composition = LoRAComposition(
            ("subject", "style"),
            "sdxl/base",
            MergeMethod.WEIGHTED,
            {"subject": 0.8, "style": 0.6},
            {"subject": {"attn.to_q": 0.7}},
            0.75,
            (EvaluationCase("portrait in watercolor", 1234),),
            {"source_sha256": "a" * 64},
            "2026-11-02T00:00:00+00:00",
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = save_composition(composition, Path(temporary) / "recipe.json")
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["merge_method"], "weighted")
        self.assertEqual(payload["layer_scales"]["subject"]["attn.to_q"], 0.7)
        self.assertEqual(payload["validation_prompts"][0]["seed"], 1234)
        self.assertEqual(payload["provenance"]["source_sha256"], "a" * 64)
