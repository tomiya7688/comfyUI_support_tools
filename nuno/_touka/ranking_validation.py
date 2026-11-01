from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol


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
# 責務: [ ScoreProvider: 候補featureを独立評価するevaluator契約を定義する ]
# フィールド: []
# 処理: []
# }
class ScoreProvider(Protocol):
    # {
    # 責務: [ score: candidate featureとpresetから評価scoreを返す ]
    # 処理: [ 1: candidateを採点する, 2: scalar scoreを返す ]
    # 引数: [ self: evaluator, features: candidate feature, object_preset: preset ]
    # 戻り値: [ score: evaluator score ]
    # }
    def score(self, features: Mapping[str, float], object_preset: str) -> float: ...


# {
# 責務: [ RankedCandidate: 複数evaluatorによる候補順位と不一致を保持する ]
# フィールド: [ candidate_index: 入力候補index, score: 統合順位score, disagreement: evaluator標準scoreの標準偏差, uncertain: 閾値超過 ]
# 処理: []
# }
@dataclass(frozen=True)
class RankedCandidate:
    candidate_index: int
    score: float
    disagreement: float
    uncertain: bool


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


# {
# 責務: [ rank_candidates: evaluator群を標準化して候補順位と不一致を計算する ]
# 処理: [ 1: evaluator別scoreを計算する, 2: scoreを標準化する, 3: 合意scoreと不一致を降順で返す ]
# 引数: [ candidates: candidate feature列, evaluators: score provider列, object_preset: preset, disagreement_threshold: uncertain閾値 ]
# 戻り値: [ ranked: 統合順位 ]
# }
def rank_candidates(
    candidates: Sequence[Mapping[str, float]],
    evaluators: Sequence[ScoreProvider],
    object_preset: str,
    *,
    disagreement_threshold: float = 1.0,
) -> list[RankedCandidate]:
    if not candidates or not evaluators:
        raise ValueError("ranking requires candidates and evaluators")
    if disagreement_threshold < 0:
        raise ValueError("disagreement_threshold cannot be negative")
    score_columns = [
        [float(evaluator.score(item, object_preset)) for item in candidates]
        for evaluator in evaluators
    ]
    normalized_columns: list[list[float]] = []
    for scores in score_columns:
        mean = sum(scores) / len(scores)
        variance = sum((score - mean) ** 2 for score in scores) / len(scores)
        deviation = variance**0.5
        normalized_columns.append(
            [(score - mean) / deviation if deviation else 0.0 for score in scores]
        )
    ranked = []
    for index in range(len(candidates)):
        values = [column[index] for column in normalized_columns]
        score = sum(values) / len(values)
        disagreement = (sum((value - score) ** 2 for value in values) / len(values)) ** 0.5
        ranked.append(
            RankedCandidate(
                candidate_index=index,
                score=score,
                disagreement=disagreement,
                uncertain=disagreement > disagreement_threshold,
            )
        )
    return sorted(ranked, key=lambda item: item.score, reverse=True)
