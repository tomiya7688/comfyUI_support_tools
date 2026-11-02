"""Bounded generation/evaluation/retry hooks for post-process integrations."""

from __future__ import annotations

from collections.abc import Callable

from .contracts import GenerationEvaluation, PromptAdjustmentResult

Generate = Callable[[PromptAdjustmentResult, int], object]
Evaluate = Callable[[object, PromptAdjustmentResult], GenerationEvaluation]
Repair = Callable[[object, tuple[str, ...], PromptAdjustmentResult], object | None]


# {
# 責務: [PromptStabilityOrchestrator: retry adapterへ有限budgetを渡す]
# フィールド: [generator, evaluator, optional local repair callback]
# 処理: [candidate評価・failure別repair・retryを明示budget内で行う]
# }
class PromptStabilityOrchestrator:
    # {
    # 責務: [__init__: generation/evaluation integration hookを保持する]
    # 処理: [1: required generator/evaluatorとoptional repairを設定する]
    # 引数: [self: orchestrator, generate: generation API, evaluate: quality evaluator, repair: local repair API]
    # 戻り値: []
    # }
    def __init__(
        self, generate: Generate, evaluate: Evaluate, repair: Repair | None = None
    ) -> None:
        self.generate = generate
        self.evaluate = evaluate
        self.repair = repair

    # {
    # 責務: [run: initial generationを評価してbounded retryを実行する]
    # 処理: [1: candidateを生成する, 2: failureを評価しrepair/retryを最大retry_limit回行う]
    # 引数: [self: orchestrator, plan: adjustment plan]
    # 戻り値: [best image and evaluation]
    # }
    def run(self, plan: PromptAdjustmentResult) -> tuple[object, GenerationEvaluation]:
        best_image: object | None = None
        best_eval: GenerationEvaluation | None = None
        for attempt in range(plan.retry_limit + 1):
            image = self.generate(plan, attempt)
            result = self.evaluate(image, plan)
            if best_eval is None or result.score > best_eval.score:
                best_image, best_eval = image, result
            if result.accepted:
                return image, result
            if attempt < plan.retry_limit and self.repair is not None and result.failure_types:
                repaired = self.repair(image, result.failure_types, plan)
                if repaired is not None:
                    repaired_result = self.evaluate(repaired, plan)
                    if repaired_result.score > best_eval.score:
                        best_image, best_eval = repaired, repaired_result
                    if repaired_result.accepted:
                        return repaired, repaired_result
        assert best_image is not None and best_eval is not None
        return best_image, best_eval
