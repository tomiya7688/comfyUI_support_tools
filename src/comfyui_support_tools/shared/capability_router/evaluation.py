"""Use-case-specific evaluator contracts without a universal quality score."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Protocol

from .contracts import GenerationUseCase


# {
#   責務: [GenerationEvaluator: task-specific image assessment interfaceを定義する]
#   フィールド: [evaluate(prompt, image_bytes, model_id) -> named score mapping]
#   処理: [別々のuse case metric breakdownを返し, 共通scoreへ潰さない]
# }
class GenerationEvaluator(Protocol):
    # {
    #   責務: [evaluate: prompt/image/capability別のnamed scoreを返す]
    #   処理: [return use-case-specific score names instead of a universal quality score]
    #   引数: [prompt: same-prompt comparison input, image_bytes: generated result, model_id: selected capability]
    #   戻り値: [Mapping[str, float]: task-specific metrics normalized to zero through one]
    # }
    def evaluate(self, prompt: str, image_bytes: bytes, model_id: str) -> Mapping[str, float]: ...


# {
#   責務: [EvaluatorRegistry: use caseごとに明示的なevaluator instanceを登録する]
#   フィールド: [GenerationUseCase to evaluator]
# }
class EvaluatorRegistry:
    # {
    #   責務: [__init__: evaluator mapを初期化する]
    #   処理: [copy the optional caller-provided evaluator mapping]
    #   引数: [evaluators: optional use-case evaluator mapping]
    #   戻り値: []
    # }
    def __init__(
        self, evaluators: Mapping[GenerationUseCase, GenerationEvaluator] | None = None
    ) -> None:
        self._evaluators = dict(evaluators or {})

    # {
    #   責務: [register: 一つのuse case用evaluatorを登録する]
    #   処理: [reject duplicate use-case registrations and store the evaluator]
    #   引数: [use_case: task family, evaluator: specialized scoring adapter]
    #   戻り値: []
    #   エラー: [ValueError: duplicate use case evaluator]
    # }
    def register(self, use_case: GenerationUseCase, evaluator: GenerationEvaluator) -> None:
        if use_case in self._evaluators:
            raise ValueError(f"an evaluator is already registered for {use_case.value}")
        self._evaluators[use_case] = evaluator

    # {
    #   責務: [get: use caseのscorerが存在する場合に取得する]
    #   処理: [return a registered evaluator without implicit fallback]
    #   引数: [use_case: requested task category]
    #   戻り値: [GenerationEvaluator | None: registered evaluator]
    # }
    def get(self, use_case: GenerationUseCase) -> GenerationEvaluator | None:
        return self._evaluators.get(use_case)

    # {
    #   責務: [evaluate: scorer breakdownをvalidateして返す]
    #   処理: [invoke the matching evaluator and validate finite normalized named scores]
    #   引数: [use_case: task category, prompt: evaluated prompt, image_bytes: generated image, model_id: capability ID]
    #   戻り値: [dict[str, float]: named metric breakdown]
    #   エラー: [LookupError: task scorer未登録, ValueError: invalid score range]
    # }
    def evaluate(
        self,
        use_case: GenerationUseCase,
        prompt: str,
        image_bytes: bytes,
        model_id: str,
    ) -> dict[str, float]:
        evaluator = self.get(use_case)
        if evaluator is None:
            raise LookupError(f"no evaluator is registered for {use_case.value}")
        scores = dict(evaluator.evaluate(prompt, image_bytes, model_id))
        if not scores or any(
            not name.strip()
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not math.isfinite(score)
            or not 0 <= score <= 1
            for name, score in scores.items()
        ):
            raise ValueError("evaluator must return named finite scores between zero and one")
        return scores
