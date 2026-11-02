"""Composable candidate exploration and draft-to-final handoff helpers."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass


# {
#   責務: [ScoredDraft: generated candidateとcaller-provided evaluator scoreを保持する]
#   フィールド: [candidate_id, image_bytes, score]
#   処理: [scoreの意味を固定せず, evaluatorの宣言をそのまま受け取る]
# }
@dataclass(frozen=True, slots=True)
class ScoredDraft:
    candidate_id: int
    image_bytes: bytes
    score: float

    def __post_init__(self) -> None:
        if self.candidate_id < 0 or not self.image_bytes:
            raise ValueError("draft candidates require a non-negative ID and image data")
        if not math.isfinite(self.score) or not 0 <= self.score <= 1:
            raise ValueError("candidate score must be a finite value between zero and one")


# {
#   責務: [DraftBatchResult: evaluator score順に整列した候補と任意のHQ画像を返す]
#   フィールド: [candidates, final_image]
# }
@dataclass(frozen=True, slots=True)
class DraftBatchResult:
    candidates: tuple[ScoredDraft, ...]
    final_image: bytes | None


# {
#   責務: [run_draft_to_final: N候補生成, caller evaluator選別, optional HQ rerenderを順序制御する]
#   処理: [全candidateを同じrequest closureで作成し, 安定したscore順に並べてbest候補のみfinal rendererへ渡す]
#   引数: [count: candidate数, generate: candidate生成, evaluate: evaluator score関数, top_k: 保持候補数, render_final: 任意のHQ renderer]
#   戻り値: [DraftBatchResult: score順候補と任意final画像]
#   エラー: [ValueError: 数量やevaluator戻り値が不正な場合]
# }
def run_draft_to_final(
    count: int,
    generate: Callable[[int], bytes],
    evaluate: Callable[[bytes], float],
    *,
    top_k: int = 1,
    render_final: Callable[[bytes], bytes] | None = None,
) -> DraftBatchResult:
    if isinstance(count, bool) or not 1 <= count <= 100:
        raise ValueError("candidate count must be between 1 and 100")
    if isinstance(top_k, bool) or not 1 <= top_k <= count:
        raise ValueError("top_k must be between one and candidate count")
    scored = []
    for candidate_id in range(count):
        image = generate(candidate_id)
        score = evaluate(image)
        scored.append(ScoredDraft(candidate_id, image, float(score)))
    ranked = tuple(sorted(scored, key=lambda candidate: (-candidate.score, candidate.candidate_id)))
    selected = ranked[:top_k]
    final_image = render_final(selected[0].image_bytes) if render_final is not None else None
    if final_image is not None and not final_image:
        raise ValueError("HQ renderer returned empty image data")
    return DraftBatchResult(selected, final_image)
