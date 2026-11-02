from __future__ import annotations

import unittest
from dataclasses import replace

from comfyui_support_tools.shared.prompt_stability.analyzer import PromptRiskAnalyzer
from comfyui_support_tools.shared.prompt_stability.contracts import (
    ContentMode,
    GenerationEvaluation,
    PromptRiskRequest,
)
from comfyui_support_tools.shared.prompt_stability.orchestration import PromptStabilityOrchestrator
from comfyui_support_tools.shared.prompt_stability.planner import PromptAdjustmentPlanner


# {
# 責務: [PromptStabilityOrchestrationTests: evaluation-driven generation loopを検証する]
# フィールド: [なし]
# 処理: [repair優先とretry budget制限を確認する]
# }
class PromptStabilityOrchestrationTests(unittest.TestCase):
    # {
    # 責務: [test_repair_precedes_bounded_retry_and_returns_accepted_candidate: failure repairとretry境界を確認する]
    # 処理: [1: failed candidateとrepair callbackを用意する, 2: 受理candidateとgeneration回数を確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_repair_precedes_bounded_retry_and_returns_accepted_candidate(self) -> None:
        request = PromptRiskRequest("crowded group", ContentMode.SFW)
        plan = replace(
            PromptAdjustmentPlanner().plan(request, PromptRiskAnalyzer().analyze(request)),
            retry_limit=2,
        )
        generated: list[int] = []

        # {
        # 責務: [generate: fixture candidateを返す]
        # 処理: [attemptを記録しcandidate IDを返す]
        # 引数: [plan, attempt]
        # 戻り値: [candidate ID]
        # }
        def generate(plan, attempt):
            generated.append(attempt)
            return f"image-{attempt}"

        # {
        # 責務: [evaluate: fixture candidate qualityを測定する]
        # 処理: [repaired candidateだけを受理する]
        # 引数: [image, plan]
        # 戻り値: [GenerationEvaluation]
        # }
        def evaluate(image, _plan):
            score = {"image-0": 0.4, "image-1": 0.5, "repaired": 0.8, "image-2": 0.3}[image]
            return GenerationEvaluation(image, score, ("hands",), image == "repaired")

        output, result = PromptStabilityOrchestrator(generate, evaluate, lambda *_: "repaired").run(
            plan
        )
        self.assertEqual(output, "repaired")
        self.assertEqual(result.score, 0.8)
        self.assertEqual(generated, [0])
        self.assertLessEqual(len(generated), plan.retry_limit + 1)


if __name__ == "__main__":
    unittest.main()
