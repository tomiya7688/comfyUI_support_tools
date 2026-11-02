"""Tests for safe training-free LoRA analysis and composition."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np

from comfyui_support_tools.shared.lora_composition import (
    EvaluationCase,
    EvaluationScore,
    LoRAAdapter,
    LoRACompositionApplication,
    LoRARole,
    MergeMethod,
    analyze_interference,
    check_composition_compatibility,
    merge_adapters,
)
from comfyui_support_tools.shared.lora_composition.io import new_composition, save_composition


# {
# 責務: [LoRACompositionTests: coordinate this module responsibility]
# フィールド: [declared values and public collaborators]
# 処理: [follow the documented contract and preserve validated invariants]
# }
class LoRACompositionTests(unittest.TestCase):
    # {
    # 責務: [setUp: create two deterministic low-rank adapters]
    # 処理: [share one module and expose distinct subject/style contributions]
    # 引数: [self: test fixture]
    # 戻り値: [None: fixtures initialized]
    # }
    def setUp(self):
        self.layer = "lora_unet_block.attn.to_q"
        self.subject = self._adapter("subject", np.eye(2), np.eye(2), LoRARole.SUBJECT)
        self.style = self._adapter("style", np.eye(2), np.diag([1.0, -1.0]), LoRARole.STYLE)

    # {
    # 責務: [_adapter: build one valid safetensors-style adapter tensor map]
    # 処理: [create paired rank-2 matrices and consistent family/provenance metadata]
    # 引数: [self: test fixture, name: adapter ID, a: down factor, b: up factor, role: functional role]
    # 戻り値: [LoRAAdapter: deterministic model update fixture]
    # }
    def _adapter(self, name, a, b, role):
        return LoRAAdapter(
            name=name,
            tensors={f"{self.layer}.lora_A.weight": a, f"{self.layer}.lora_B.weight": b},
            family="sdxl",
            architecture="SDXL",
            rank=2,
            alpha=2.0,
            role=role,
            provenance={"source_sha256": name * 16},
        )

    # {
    # 責務: [test_preflight_rejects_family_architecture_and_target_mismatch: reject unsafe merges]
    # 処理: [verify base-family mismatch and unknown architecture are blocking]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_preflight_rejects_family_architecture_and_target_mismatch(self):
        family_conflict = self._adapter("flux", np.eye(2), np.eye(2), LoRARole.CONCEPT)
        object.__setattr__(family_conflict, "family", "flux")
        report = check_composition_compatibility(
            (self.subject, family_conflict), "sdxl/base", "SDXL"
        )
        self.assertFalse(report.compatible)
        self.assertIn("family_mismatch", {finding.code for finding in report.findings})
        with self.assertRaisesRegex(ValueError, "preflight"):
            merge_adapters((self.subject, family_conflict), "sdxl/base", "SDXL")
        architecture_report = check_composition_compatibility(
            (self.subject, self.style), "sdxl/base", "FLUX"
        )
        self.assertIn(
            "base_architecture_mismatch",
            {finding.code for finding in architecture_report.findings},
        )
        unknown_architecture = check_composition_compatibility(
            (self.subject, self.style), "sdxl/base"
        )
        self.assertFalse(unknown_architecture.compatible)

    # {
    # 責務: [test_interference_reports_opposed_updates_and_layer_spectrum: expose conflict signals]
    # 処理: [compare identical and reversed update directions for shared layer]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_interference_reports_opposed_updates_and_layer_spectrum(self):
        findings = analyze_interference((self.subject, self.style))
        self.assertEqual(len(findings), 1)
        self.assertLess(findings[0].cosine_similarity, 0.1)
        self.assertAlmostEqual(findings[0].sign_conflict_fraction, 0.5)
        self.assertEqual(findings[0].layer, self.layer)
        self.assertTrue(findings[0].left_singular_values)

    # {
    # 責務: [test_weighted_merge_preserves_sum_and_role_aware_modes_are_deterministic: compare merge rules]
    # 処理: [reconstruct low-rank outputs and ensure top-K sparsifies conflicting updates]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_weighted_merge_preserves_sum_and_role_aware_modes_are_deterministic(self):
        adapters = (self.subject, self.style)
        weighted = merge_adapters(adapters, "sdxl/base", "SDXL", {"subject": 0.5, "style": 1.0})
        actual = weighted[f"{self.layer}.lora_B.weight"] @ weighted[f"{self.layer}.lora_A.weight"]
        expected = np.diag([1.5, -0.5])
        np.testing.assert_allclose(actual, expected, atol=1e-5)
        top_k = merge_adapters(
            adapters, "sdxl/base", "SDXL", method=MergeMethod.TOP_K, top_k_fraction=0.5
        )
        top_update = top_k[f"{self.layer}.lora_B.weight"] @ top_k[f"{self.layer}.lora_A.weight"]
        self.assertLessEqual(np.count_nonzero(top_update), 2)
        zip_first = merge_adapters(adapters, "sdxl/base", "SDXL", method=MergeMethod.ZIP_STYLE)
        zip_second = merge_adapters(adapters, "sdxl/base", "SDXL", method=MergeMethod.ZIP_STYLE)
        for key in zip_first:
            np.testing.assert_array_equal(zip_first[key], zip_second[key])

    # {
    # 責務: [test_layer_scale_overrides_global_scale: honor per-module settings]
    # 処理: [apply a local adapter override and reconstruct expected output]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_layer_scale_overrides_global_scale(self):
        merged = merge_adapters(
            (self.subject, self.style),
            "sdxl/base",
            "SDXL",
            {"subject": 0.0, "style": 0.0},
            layer_scales={"subject": {self.layer: 1.0}, "style": {self.layer: 0.25}},
        )
        update = merged[f"{self.layer}.lora_B.weight"] @ merged[f"{self.layer}.lora_A.weight"]
        np.testing.assert_allclose(update, np.diag([1.25, 0.75]), atol=1e-5)

    # {
    # 責務: [test_search_evaluates_fixed_seed_grid_and_layer_weights: rank reproducible candidates]
    # 処理: [evaluate candidate scales with fixed cases and select metric-driven optimum]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_search_evaluates_fixed_seed_grid_and_layer_weights(self):
        app = LoRACompositionApplication(candidate_budget=100)
        cases = (EvaluationCase("subject in style", 123), EvaluationCase("portrait", 123))
        seen = []

        # {
        # 責務: [evaluate: perform the declared operation]
        # 処理: [follow the documented contract and preserve validated invariants]
        # 引数: [declared function inputs]
        # 戻り値: [declared function result]
        # }
        def evaluate(adapters, scales, layers, case):
            seen.append((dict(scales), case.seed, dict(layers)))
            score = 1.0 - abs(scales["subject"] - 0.75)
            return EvaluationScore(score, score, score, score)

        results = app.search_scales(
            (self.subject, self.style),
            cases,
            evaluate,
            (0.25, 0.75, 1.0),
            {self.layer: {"subject": (0.5, 0.75)}},
        )
        self.assertEqual(results[0].global_scales["subject"], 0.75)
        self.assertEqual(len(seen), 3 * 3 * 2 * 2)
        self.assertEqual({seed for _, seed, _ in seen}, {123})
        self.assertIn(self.layer, results[0].layer_scales["subject"])

    # {
    # 責務: [test_search_compositions_compares_static_methods_with_runtime_stacking: expose baselines]
    # 処理: [evaluate runtime stack plus every requested static method using a fixed seed]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_search_compositions_compares_static_methods_with_runtime_stacking(self):
        app = LoRACompositionApplication(candidate_budget=20)
        seen = []

        # {
        # 責務: [evaluate: perform the declared operation]
        # 処理: [follow the documented contract and preserve validated invariants]
        # 引数: [declared function inputs]
        # 戻り値: [declared function result]
        # }
        def evaluate(adapters, scales, layers, case, method):
            seen.append(method)
            value = 0.7 if method is None else 0.9 if method is MergeMethod.WEIGHTED else 0.8
            return EvaluationScore(value, value, value, value)

        results = app.search_compositions(
            (self.subject, self.style),
            (EvaluationCase("same prompt", 42),),
            evaluate,
            scale_grid=(1.0,),
        )
        self.assertIn(None, seen)
        self.assertIn(MergeMethod.K_LORA, seen)
        self.assertEqual(results[0].merge_method, MergeMethod.WEIGHTED)
        self.assertEqual(len(results), 6)

    # {
    # 責務: [test_search_rejects_oversized_grid_and_invalid_evaluator_metrics: bound evaluation work]
    # 処理: [reject candidate explosions before rendering and non-normalized output metrics]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_search_rejects_oversized_grid_and_invalid_evaluator_metrics(self):
        app = LoRACompositionApplication(candidate_budget=4)
        case = (EvaluationCase("prompt", 7),)
        with self.assertRaisesRegex(ValueError, "budget"):
            app.search_scales(
                (self.subject, self.style),
                case,
                lambda *_: EvaluationScore(1, 1, 1, 1),
                (0.1, 0.2, 0.3),
            )
        with self.assertRaisesRegex(ValueError, "finite metrics"):
            LoRACompositionApplication().search_scales(
                (self.subject, self.style), case, lambda *_: EvaluationScore(2, 1, 1, 1), (1.0,)
            )

    # {
    # 責務: [test_preference_history_becomes_scale_prior: reuse user selections]
    # 処理: [persist choices and include their mean as a future candidate]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_preference_history_becomes_scale_prior(self):
        with tempfile.TemporaryDirectory() as directory:
            app = LoRACompositionApplication(Path(directory) / "preferences.json")
            app.record_preference((self.subject, self.style), {"subject": 0.8, "style": 0.4})
            self.assertEqual(app.preference_priors(), {"subject": 0.8, "style": 0.4})
            results = app.search_scales(
                (self.subject, self.style),
                (EvaluationCase("prompt", 1),),
                lambda *_: EvaluationScore(0.5, 0.5, 0.5, 0.5),
                (1.0,),
            )
            self.assertTrue(any(item.global_scales["subject"] == 0.8 for item in results))

    # {
    # 責務: [test_runtime_recipe_round_trips_as_portable_json: preserve non-destructive settings]
    # 処理: [serialize source names, method, scales, prompt seeds, score and provenance]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    def test_runtime_recipe_round_trips_as_portable_json(self):
        with tempfile.TemporaryDirectory() as directory:
            recipe = new_composition(
                (self.subject, self.style),
                "sdxl/base",
                MergeMethod.WEIGHTED,
                {"subject": 0.8, "style": 0.6},
                score=0.9,
                cases=(EvaluationCase("prompt", 11),),
            )
            saved = save_composition(recipe, Path(directory) / "composition.json")
            content = saved.read_text(encoding="utf-8")
            self.assertIn('"merge_method": "weighted"', content)
            self.assertIn('"seed": 11', content)
            self.assertIn("source_sha256", content)

    # {
    # 責務: [test_safetensors_load_merge_export_preserves_metadata_and_refuses_overwrite: verify real artifacts]
    # 処理: [load source files, export static merged weights plus recipe, then block replacing outputs]
    # 引数: [self: test case]
    # 戻り値: [None: assertions pass]
    # }
    @unittest.skipUnless(
        importlib.util.find_spec("safetensors"), "optional safetensors package not installed"
    )
    def test_safetensors_load_merge_export_preserves_metadata_and_refuses_overwrite(self):
        from safetensors import safe_open
        from safetensors.numpy import load_file, save_file

        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, update in (("subject", np.eye(2)), ("style", np.diag([1.0, -1.0]))):
                path = Path(directory) / f"{name}.safetensors"
                save_file(
                    {
                        f"{self.layer}.lora_A.weight": np.eye(2, dtype=np.float32),
                        f"{self.layer}.lora_B.weight": update.astype(np.float32),
                    },
                    str(path),
                    metadata={
                        "base_model_family": "sdxl",
                        "architecture": "SDXL",
                        "ss_network_dim": "2",
                        "ss_network_alpha": "2",
                    },
                )
                paths.append(path)
            app = LoRACompositionApplication()
            adapters = app.load(paths, {"subject": "subject", "style": "style"})
            recipe = app.export(
                adapters,
                "sdxl/base",
                "SDXL",
                MergeMethod.WEIGHTED,
                {"subject": 1.0, "style": 1.0},
                Path(directory) / "composition.json",
                cases=(EvaluationCase("same prompt", 17),),
                score=0.8,
            )
            self.assertTrue(recipe.static_merged_lora.is_file())
            merged_tensors = load_file(str(recipe.static_merged_lora))
            self.assertIn(f"{self.layer}.lora_A.weight", merged_tensors)
            with safe_open(str(recipe.static_merged_lora), framework="numpy") as merged:
                self.assertEqual(merged.metadata()["base_model_family"], "sdxl")
                self.assertEqual(merged.metadata()["merge_method"], "weighted")
            with self.assertRaises(FileExistsError):
                app.export(
                    adapters,
                    "sdxl/base",
                    "SDXL",
                    MergeMethod.WEIGHTED,
                    {"subject": 1.0, "style": 1.0},
                    Path(directory) / "composition.json",
                )


if __name__ == "__main__":
    unittest.main()
