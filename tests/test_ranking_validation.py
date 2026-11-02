import unittest

from nuno._touka.candidate_evaluator import EvaluationResult
from nuno._touka.ranking_validation import rank_candidates, validate_ranking


# {
# 責務: [ RankingValidationTests: Touka candidate ranker validation metricsを検証する ]
# フィールド: []
# 処理: [ 1: 一致/不一致rankingを検証する, 2: 不正入力を検証する ]
# }
class RankingValidationTests(unittest.TestCase):
    # {
    # 責務: [ _FakeScoreProvider: 共通evaluator contractでfixture scoreを返す ]
    # フィールド: [ feature: 参照feature, reverse: score反転 ]
    # 処理: []
    # }
    class _FakeScoreProvider:
        # {
        # 責務: [ __init__: score providerのfixture設定を保持する ]
        # 処理: [ 1: feature名と反転設定を保存する ]
        # 引数: [ self: instance, feature: 読み取るmetric, reverse: 順序反転 ]
        # 戻り値: []
        # }
        def __init__(self, feature, reverse=False):
            self.feature = feature
            self.reverse = reverse

        # {
        # 責務: [ evaluate: fixture candidateを共通結果contractで採点する ]
        # 処理: [ 1: metricを読む, 2: 必要なら順序を反転する 3: provenanceを付けて返す ]
        # 引数: [ self: instance, features: candidate feature, object_preset: unused preset ]
        # 戻り値: [ EvaluationResult ]
        # }
        def evaluate(self, features, object_preset):
            value = features[self.feature]
            score = -value if self.reverse else value
            return EvaluationResult(score, {self.feature: score}, "test.fake", "1")

    # {
    # 責務: [ test_reports_perfect_ranking_and_top_k: synthetic GTの一致指標を確認する ]
    # 処理: [ 1: GT一致scoreを評価する, 2: 指標を確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_reports_perfect_ranking_and_top_k(self):
        result = validate_ranking([0.9, 0.5, 0.1], [0.95, 0.5, 0.1], top_k=2)
        self.assertEqual(result.pairwise_accuracy, 1.0)
        self.assertEqual(result.top1_accuracy, 1.0)
        self.assertEqual(result.top_k_inclusion, 1.0)

    # {
    # 責務: [ test_reports_rank_failure: poor ranking is exposed by the metrics ]
    # 処理: [ 1: reversed scoreを評価する, 2: failure metricsを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_reports_rank_failure(self):
        result = validate_ranking([0.1, 0.9, 0.5], [0.95, 0.5, 0.1], top_k=1)
        self.assertEqual(result.top1_accuracy, 0.0)
        self.assertEqual(result.top_k_inclusion, 0.0)
        self.assertLess(result.pairwise_accuracy, 1.0)

    # {
    # 責務: [ test_rejects_mismatched_validation_data: 対応しないGTを拒否する ]
    # 処理: [ 1: 長さ不一致を渡す, 2: ValueErrorを確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_rejects_mismatched_validation_data(self):
        with self.assertRaises(ValueError):
            validate_ranking([0.5], [])

    # {
    # 責務: [ test_combines_multiple_evaluators_and_flags_disagreement: evaluator順位統合と不一致を確認する ]
    # 処理: [ 1: 合意候補をrankする, 2: 逆順位evaluatorの不一致を確認する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_combines_multiple_evaluators_and_flags_disagreement(self):
        candidates = [{"shape": 3.0}, {"shape": 2.0}, {"shape": 1.0}]
        agreement = rank_candidates(
            candidates,
            [self._FakeScoreProvider("shape"), self._FakeScoreProvider("shape")],
            "generic",
        )
        self.assertEqual(agreement[0].candidate_index, 0)
        disagreement = rank_candidates(
            candidates,
            [
                self._FakeScoreProvider("shape"),
                self._FakeScoreProvider("shape", reverse=True),
            ],
            "generic",
            disagreement_threshold=0.5,
        )
        self.assertTrue(disagreement[0].uncertain)
        self.assertGreater(disagreement[0].disagreement, 0.5)


if __name__ == "__main__":
    unittest.main()
