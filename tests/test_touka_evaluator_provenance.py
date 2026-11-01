import json
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).parents[1] / "scripts" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from touka_evaluator import ToukaEvaluator  # noqa: E402


# {
# 責務: [ ToukaEvaluatorProvenanceTests: candidate評価のprovenance集計を検証する ]
# フィールド: []
# 処理: [ 1: versionとbreakdownを含む候補を読み込む, 2: 集計結果を確認する ]
# }
class ToukaEvaluatorProvenanceTests(unittest.TestCase):
    # {
    # 責務: [ test_aggregates_candidate_evaluator_provenance: versionとmetric寄与を保持して集計する ]
    # 処理: [ 1: candidate score jsonを作る, 2: evaluator集計を検証する ]
    # 引数: [ self: test instance ]
    # 戻り値: []
    # }
    def test_aggregates_candidate_evaluator_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "candidate_scores.json").write_text(
                json.dumps(
                    [
                        {
                            "score": 2.0,
                            "evaluator_id": "touka.heuristic_baseline",
                            "evaluator_version": "touka-heuristic-v1",
                            "score_breakdown": {"edge_gain": 1.0},
                        },
                        {
                            "score": 4.0,
                            "evaluator_id": "touka.heuristic_baseline",
                            "evaluator_version": "touka-heuristic-v1",
                            "score_breakdown": {"edge_gain": 3.0},
                        },
                    ]
                ),
                encoding="utf-8",
            )
            result = ToukaEvaluator().evaluate_candidates(output)
        self.assertEqual(
            result["evaluator_provenance"],
            [{"evaluator_id": "touka.heuristic_baseline", "version": "touka-heuristic-v1"}],
        )
        self.assertEqual(result["mean_score_breakdown"], {"edge_gain": 2.0})


if __name__ == "__main__":
    unittest.main()
