import unittest

from nuno._touka.candidate_evaluator import (
    CALIBRATED_LINEAR_VERSION,
    HEURISTIC_BASELINE_VERSION,
    CalibratedLinearEvaluator,
    HeuristicBaselineEvaluator,
    calibrate_linear_evaluator,
)
from nuno._touka.ranking_validation import rank_candidates


# {
# 責務: [ CandidateEvaluatorTests: Touka baseline evaluator契約を検証する ]
# フィールド: []
# 処理: [ 1: versionとbreakdownを検証する, 2: preset境界を検証する ]
# }
class CandidateEvaluatorTests(unittest.TestCase):
    # {
    # 責務: [ test_returns_versioned_metric_breakdown: scoreと寄与metricの合計が一致することを確認する ]
    # 処理: [ 1: sample metricを評価する, 2: versionとscore集計を検証する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_returns_versioned_metric_breakdown(self):
        result = HeuristicBaselineEvaluator().evaluate(
            {
                "information_gain": 2.0,
                "edge_gain": 0.5,
                "shape_score": 3.0,
                "tracking_confidence": 0.8,
                "noise": 100.0,
            },
            "generic",
        )
        self.assertEqual(result.version, HEURISTIC_BASELINE_VERSION)
        self.assertEqual(result.evaluator_id, "touka.heuristic_baseline")
        self.assertEqual(result.score, sum(result.breakdown.values()))
        self.assertAlmostEqual(result.score, 28.36)
        self.assertIn("noise_penalty", result.breakdown)

    # {
    # 責務: [ test_rejects_unknown_preset: 未知presetを明示的に拒否する ]
    # 処理: [ 1: 不明presetを評価する, 2: ValueErrorを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_rejects_unknown_preset(self):
        with self.assertRaises(ValueError):
            HeuristicBaselineEvaluator().evaluate({}, "unknown")

    # {
    # 責務: [ test_applies_named_preset_bonus: preset寄与を内訳へ含める ]
    # 処理: [ 1: shirt候補を評価する, 2: preset寄与を確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_applies_named_preset_bonus(self):
        result = HeuristicBaselineEvaluator().evaluate(
            {"area_ratio": 0.1, "symmetry": 0.5}, "shirt"
        )
        self.assertAlmostEqual(result.breakdown["preset_bonus"], 1.4)

    # {
    # 責務: [test_calibrates_linear_weights_from_quality_labels: labeled examplesから係数をfitする]
    # 処理: [1: monotonic validation setをfitする 2: provenanceと順位を確認する]
    # 引数: [self: test instance]
    # 戻り値: []
    # }
    def test_calibrates_linear_weights_from_quality_labels(self):
        evaluator = calibrate_linear_evaluator(
            [{"edge": 0.0}, {"edge": 1.0}, {"edge": 2.0}],
            [1.0, 3.0, 5.0],
        )
        self.assertIsInstance(evaluator, CalibratedLinearEvaluator)
        self.assertEqual(evaluator.version, CALIBRATED_LINEAR_VERSION)
        self.assertAlmostEqual(evaluator.weights["edge"], 2.0, places=5)
        self.assertAlmostEqual(evaluator.intercept, 1.0, places=5)
        self.assertLess(
            evaluator.evaluate({"edge": 0.0}, "generic").score,
            evaluator.evaluate({"edge": 2.0}, "generic").score,
        )
        ranked = rank_candidates([{"edge": 0.0}, {"edge": 2.0}], [evaluator], "generic")
        self.assertEqual(ranked[0].candidate_index, 1)

    # {
    # 責務: [test_rejects_invalid_calibration_examples: 不正labelとshapeを拒否する]
    # 処理: [1: mismatch/non-finite入力をfitする 2: ValueErrorを確認する]
    # 引数: [self: test instance]
    # 戻り値: []
    # }
    def test_rejects_invalid_calibration_examples(self):
        with self.assertRaises(ValueError):
            calibrate_linear_evaluator([{"edge": 1.0}], [1.0])
        with self.assertRaises(ValueError):
            calibrate_linear_evaluator([{"edge": float("nan")}, {"edge": 1.0}], [0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
