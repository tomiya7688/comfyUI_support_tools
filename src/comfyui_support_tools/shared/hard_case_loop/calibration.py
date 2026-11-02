"""Feedback-based confidence calibration summaries for local Touka results."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable

from .contracts import HardCaseRecord


# {
#   責務: [ReliabilityBin: one calibration intervalのconfidence/accuracyを示す]
#   フィールド: [lower_bound, upper_bound, sample_count, mean_confidence, accuracy]
# }
@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_confidence: float
    accuracy: float


# {
#   責務: [ConfidenceCalibrationReport: feedback-label subsetでcalibration qualityをまとめる]
#   フィールド: [sample_count, expected_calibration_error, accuracy, bins, high_confidence_errors]
# }
@dataclass(frozen=True, slots=True)
class ConfidenceCalibrationReport:
    sample_count: int
    expected_calibration_error: float
    accuracy: float
    bins: tuple[ReliabilityBin, ...]
    high_confidence_errors: tuple[str, ...]

    # {
    #   責務: [to_document: reportをJSON-compatible schemaへ変換する]
    #   処理: [preserve bin-level calibration data and explicit warning on sample coverage]
    #   引数: [self: calibration report]
    #   戻り値: [dict[str, object]: portable diagnostics]
    # }
    def to_document(self) -> dict[str, object]:
        return {
            "schema": "touka-confidence-calibration.v1",
            **asdict(self),
            "note": "Feedback subset calibration only; raw confidence is not a probability estimate.",
        }


# {
#   責務: [calibrate_confidence: explicit feedbackからECEとhigh-confidence errorを計算する]
#   処理: [bin selected-candidate confidence and compare against preferred/rejected feedback labels]
#   引数: [records: local hard-case history, bin_count: reliability bins, high_confidence_threshold: error alert cutoff]
#   戻り値: [ConfidenceCalibrationReport: labeled-subset calibration metrics]
# }
def calibrate_confidence(
    records: Iterable[HardCaseRecord], bin_count: int = 10, high_confidence_threshold: float = 0.8
) -> ConfidenceCalibrationReport:
    if isinstance(bin_count, bool) or not isinstance(bin_count, int) or bin_count < 1:
        raise ValueError("bin_count must be a positive integer")
    if (
        isinstance(high_confidence_threshold, bool)
        or not isinstance(high_confidence_threshold, (int, float))
        or not math.isfinite(high_confidence_threshold)
        or not 0 <= high_confidence_threshold <= 1
    ):
        raise ValueError("high_confidence_threshold must be finite and normalized")
    labeled = []
    high_errors = []
    for record in records:
        if not record.feedback_received or not record.selected_candidate:
            continue
        selected = next(
            (
                candidate
                for candidate in record.candidates
                if candidate.candidate_id == record.selected_candidate
            ),
            None,
        )
        if selected is None:
            continue
        correct = (
            selected.candidate_id == record.user_preferred_candidate
            if record.user_preferred_candidate
            else selected.candidate_id not in record.rejected_candidates
        )
        labeled.append((selected.confidence, float(correct), record.record_id))
        if selected.confidence >= high_confidence_threshold and not correct:
            high_errors.append(record.record_id)
    bin_results = []
    ece = 0.0
    for index in range(bin_count):
        lower, upper = index / bin_count, (index + 1) / bin_count
        members = [
            item
            for item in labeled
            if lower <= item[0] < upper or (index == bin_count - 1 and item[0] == 1.0)
        ]
        if not members:
            bin_results.append(ReliabilityBin(lower, upper, 0, 0.0, 0.0))
            continue
        mean_confidence = sum(item[0] for item in members) / len(members)
        accuracy = sum(item[1] for item in members) / len(members)
        ece += len(members) / max(len(labeled), 1) * abs(mean_confidence - accuracy)
        bin_results.append(ReliabilityBin(lower, upper, len(members), mean_confidence, accuracy))
    accuracy = sum(item[1] for item in labeled) / max(len(labeled), 1)
    return ConfidenceCalibrationReport(
        len(labeled), ece, accuracy, tuple(bin_results), tuple(sorted(high_errors))
    )
