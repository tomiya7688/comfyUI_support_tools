"""Focused score direction and overfit-regression tests."""

from __future__ import annotations

import unittest

from comfyui_support_tools.shared.training_doctor import (
    EarlyStopPolicy,
    ScorePreset,
    ScoreWeights,
    ValidationTask,
    score_weights_for_task,
)
from comfyui_support_tools.shared.training_doctor.scoring import overfit_signals, score_metrics


# {
# 責務: [TrainingDoctorScoringTests: verify score orientation and independent regression signals]
# フィールド: [none: pure functions use deterministic metric fixtures]
# 処理: [assert penalties reduce scores, fidelity preset changes relative weight, and regressions explain stopping]
# 引数: [None: unittest fixture]
# 戻り値: [None: tests report scoring contract]
# }
class TrainingDoctorScoringTests(unittest.TestCase):
    # {
    # 責務: [test_leakage_and_memorization_are_penalties: enforce correct score direction]
    # 処理: [hold positive axes fixed while increasing both overfit dimensions]
    # 引数: [self: test case]
    # 戻り値: [None: lower score confirms both axes are penalties]
    # }
    def test_leakage_and_memorization_are_penalties(self):
        weights = ScoreWeights()
        clean, _ = score_metrics(
            {
                "fidelity": 0.8,
                "controllability": 0.8,
                "quality": 0.8,
                "diversity": 0.8,
                "base_preservation": 0.8,
                "leakage": 0.1,
                "memorization": 0.1,
            },
            weights,
        )
        overfit, breakdown = score_metrics(
            {
                "fidelity": 0.8,
                "controllability": 0.8,
                "quality": 0.8,
                "diversity": 0.8,
                "base_preservation": 0.8,
                "leakage": 0.7,
                "memorization": 0.7,
            },
            weights,
        )
        self.assertLess(overfit, clean)
        self.assertEqual(breakdown["leakage"], 0.7)

    # {
    # 責務: [test_fidelity_preset_increases_only_fidelity_priority: preserve explicit scoring intent]
    # 処理: [compare task defaults with fidelity-oriented weights]
    # 引数: [self: test case]
    # 戻り値: [None: fidelity axis receives the greater weight]
    # }
    def test_fidelity_preset_increases_only_fidelity_priority(self):
        balanced = score_weights_for_task(ValidationTask.CHARACTER)
        fidelity = score_weights_for_task(ValidationTask.CHARACTER, ScorePreset.FIDELITY)
        self.assertGreater(fidelity.fidelity, balanced.fidelity)
        for name in vars(balanced):
            if name != "fidelity":
                self.assertEqual(getattr(fidelity, name), getattr(balanced, name))

    # {
    # 責務: [test_overfit_signals_require_threshold_and_name_each_regression: explain measured risk]
    # 処理: [compare multi-axis quality deltas below and above the configured threshold]
    # 引数: [self: test case]
    # 戻り値: [None: only material regressions receive named signals]
    # }
    def test_overfit_signals_require_threshold_and_name_each_regression(self):
        previous = {
            "fidelity": 0.7,
            "controllability": 0.9,
            "quality": 0.9,
            "diversity": 0.9,
            "base_preservation": 0.9,
            "leakage": 0.1,
            "memorization": 0.1,
        }
        current = {
            **previous,
            "fidelity": 0.8,
            "controllability": 0.7,
            "base_preservation": 0.7,
            "leakage": 0.3,
        }
        signals = overfit_signals(current, previous, EarlyStopPolicy(signal_threshold=0.15))
        self.assertIn("controllability declined", signals)
        self.assertIn("base-model preservation declined", signals)
        self.assertIn("trigger-free concept leakage increased", signals)
        self.assertIn("fidelity rose while another quality axis regressed", signals)


if __name__ == "__main__":
    unittest.main()
