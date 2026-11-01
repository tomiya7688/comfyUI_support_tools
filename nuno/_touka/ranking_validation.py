from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence


# {
# 責務: [ RankingValidation: GTとの候補順位一致指標を保持する ]
# フィールド: [ pairwise_accuracy: ペア比較一致率, top1_accuracy: 最良候補選択率, top_k_inclusion: top-k良候補包含率 ]
# 処理: []
# }
@dataclass(frozen=True)
class RankingValidation:
    pairwise_accuracy: float
    top1_accuracy: float
    top_k_inclusion: float
    candidate_count: int


# {
# 責務: [ validate_ranking: evaluator順位をGT品質ラベルと比較する ]
# 処理: [ 1: 入力を検証する, 2: pairwise一致率を計算する, 3: top-k指標を返す ]
# 引数: [ scores: evaluator score, ground_truth_quality: 大きいほど良い品質値, top_k: 上位候補数, acceptable_gap: 良候補とみなすGT差 ]
# 戻り値: [ result: ranking validation metric ]
# }
def validate_ranking(
    scores: Sequence[float],
    ground_truth_quality: Sequence[float],
    *,
    top_k: int = 3,
    acceptable_gap: float = 0.0,
) -> RankingValidation:
    if len(scores) != len(ground_truth_quality):
        raise ValueError("scores and ground_truth_quality must have equal lengths")
    if not scores:
        raise ValueError("ranking validation requires at least one candidate")
    if top_k < 1 or acceptable_gap < 0:
        raise ValueError("top_k must be positive and acceptable_gap cannot be negative")

    predicted = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
    truth = sorted(
        range(len(ground_truth_quality)),
        key=lambda index: ground_truth_quality[index],
        reverse=True,
    )
    pairs = list(combinations(range(len(scores)), 2))
    correct = sum(
        (scores[first] - scores[second])
        * (ground_truth_quality[first] - ground_truth_quality[second])
        > 0
        for first, second in pairs
    )
    comparable = sum(
        ground_truth_quality[first] != ground_truth_quality[second]
        and scores[first] != scores[second]
        for first, second in pairs
    )
    best_quality = ground_truth_quality[truth[0]]
    good = {
        index
        for index, quality in enumerate(ground_truth_quality)
        if best_quality - quality <= acceptable_gap
    }
    return RankingValidation(
        pairwise_accuracy=correct / comparable if comparable else 1.0,
        top1_accuracy=float(predicted[0] == truth[0]),
        top_k_inclusion=float(bool(set(predicted[:top_k]) & good)),
        candidate_count=len(scores),
    )
