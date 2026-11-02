"""Fixed hard-case regression and local retraining/reranking exports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Protocol

from .contracts import CandidateEvidence, HardCaseRecord


# {
#   責務: [HardCaseEvaluator: record/model/configごとにcandidate scoringを実行するinterface]
#   フィールド: [evaluate]
#   処理: [allow local Touka variants to plug into fixed regression runner]
# }
class HardCaseEvaluator(Protocol):
    # {
    #   責務: [evaluate: one local hard-case inputをcandidate metricsへ評価する]
    #   処理: [return raw normalized candidate scores and confidence for supplied model/config]
    #   引数: [record: local input metadata, model_version: version ID, config_fingerprint: config ID]
    #   戻り値: [tuple[CandidateEvidence, ...]: ranked candidate evidence]
    # }
    def evaluate(
        self,
        record: HardCaseRecord,
        model_version: str,
        config_fingerprint: str,
    ) -> tuple[CandidateEvidence, ...]: ...


# {
#   責務: [RegressionRunReport: one model/config regression resultを保存可能にする]
#   フィールド: [version, count, top-k preference inclusion, catastrophe count]
# }
@dataclass(frozen=True, slots=True)
class RegressionRunReport:
    model_version: str
    config_fingerprint: str
    sample_count: int
    top1_preference_rate: float
    top3_preference_rate: float
    top5_preference_rate: float
    catastrophic_failure_count: int
    cases: tuple[dict[str, object], ...]

    # {
    #   責務: [to_document: model/config結果をversioned JSONへserializeする]
    #   処理: [keep per-case candidate ranking with aggregate Top-N metrics]
    #   引数: [self: regression result]
    #   戻り値: [dict[str, object]: regression report]
    # }
    def to_document(self) -> dict[str, object]:
        return {"schema": "touka-hard-case-regression.v1", **asdict(self)}


# {
#   責務: [run_regression_set: fixed user-confirmed hard casesをmodel/configへ再評価する]
#   処理: [exclude records without explicit human preference and measure top-k inclusion]
#   引数: [records: fixed regression set, evaluator: injected local backend, model_version: version ID, config_fingerprint: config ID]
#   戻り値: [RegressionRunReport: comparable regression metrics]
# }
def run_regression_set(
    records: Iterable[HardCaseRecord],
    evaluator: HardCaseEvaluator,
    model_version: str,
    config_fingerprint: str,
) -> RegressionRunReport:
    fixed = tuple(
        record
        for record in records
        if record.in_regression_set and record.feedback_received and record.user_preferred_candidate
    )

    case_reports = []
    hits = {1: 0, 3: 0, 5: 0}
    catastrophic = 0
    for record in fixed:
        candidates = evaluator.evaluate(record, model_version, config_fingerprint)
        ranked = tuple(sorted(candidates, key=lambda item: (-item.score, item.candidate_id)))
        ranked_ids = tuple(item.candidate_id for item in ranked)
        preferred_rank = (
            ranked_ids.index(record.user_preferred_candidate) + 1
            if record.user_preferred_candidate in ranked_ids
            else None
        )
        rejected_top = bool(ranked_ids and ranked_ids[0] in record.rejected_candidates)
        if preferred_rank is not None:
            for cutoff in hits:
                hits[cutoff] += int(preferred_rank <= cutoff)
        if preferred_rank is None or preferred_rank > 5 or rejected_top:
            catastrophic += 1
        case_reports.append(
            {
                "record_id": record.record_id,
                "preferred_candidate": record.user_preferred_candidate,
                "preferred_rank": preferred_rank,
                "top_candidate": ranked_ids[0] if ranked_ids else "",
                "top_candidate_rejected": rejected_top,
                "candidate_scores": [asdict(candidate) for candidate in ranked],
                "source_sha256": record.input_sha256,
            }
        )
    count = len(fixed)
    denominator = max(count, 1)
    return RegressionRunReport(
        model_version,
        config_fingerprint,
        count,
        hits[1] / denominator,
        hits[3] / denominator,
        hits[5] / denominator,
        catastrophic,
        tuple(case_reports),
    )


# {
#   責務: [compare_model_configs: multiple model/config candidatesを同じfixed setで比較する]
#   処理: [run an identical labeled case set through each injected local evaluator]
#   引数: [records: fixed regression cases, configurations: ordered model/config/evaluator triples]
#   戻り値: [tuple[RegressionRunReport, ...]: directly comparable Top-N reports]
# }
def compare_model_configs(
    records: Iterable[HardCaseRecord],
    configurations: tuple[tuple[str, str, HardCaseEvaluator], ...],
) -> tuple[RegressionRunReport, ...]:
    fixed = tuple(records)
    return tuple(
        run_regression_set(fixed, evaluator, model_version, config_fingerprint)
        for model_version, config_fingerprint, evaluator in configurations
    )


# {
#   責務: [export_active_learning_manifest: selected hard casesをretraining/reranking用JSONへ出力する]
#   処理: [write metadata/path/hash/feedback only and never copy or upload image bytes]
#   引数: [records: selected examples, destination: caller-selected local JSON path]
#   戻り値: [Path: written manifest]
# }
def export_active_learning_manifest(records: Iterable[HardCaseRecord], destination: Path) -> Path:
    selected = tuple(records)
    value = {
        "schema": "touka-active-learning.v1",
        "privacy": "local_references_only",
        "records": [record.to_document() for record in selected],
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
