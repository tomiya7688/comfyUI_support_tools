import unittest

from nuno._touka.ranking_validation import validate_ranking


# {
# 責務: [ RankingValidationTests: Touka candidate ranker validation metricsを検証する ]
# フィールド: []
# 処理: [ 1: 一致/不一致rankingを検証する, 2: 不正入力を検証する ]
# }
class RankingValidationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
