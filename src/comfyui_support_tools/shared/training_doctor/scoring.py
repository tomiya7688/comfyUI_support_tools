"""Balanced checkpoint scoring and explainable overfit signal detection."""

from __future__ import annotations

from collections.abc import Iterable
from statistics import fmean

from .contracts import (
    EarlyStopPolicy,
    ImageMetrics,
    ScorePreset,
    ScoreWeights,
    ValidationSample,
    ValidationTask,
)


# {
# 責務: [metric_means: aggregate independent normalized image quality axes]
# 処理: [average each fidelity, control, preservation, leakage, memorization and diversity dimension]
# 引数: [samples: measurements for one checkpoint and one LoRA strength]
# 戻り値: [dict[str, float]: mean quality axes]
# エラー: [ValueError: samples are empty]
# }
def metric_means(samples: Iterable[ValidationSample]) -> dict[str, float]:
    rows = tuple(samples)
    if not rows:
        raise ValueError("cannot score an empty validation result")
    names = tuple(ImageMetrics.__dataclass_fields__)
    return {name: fmean(getattr(sample.metrics, name) for sample in rows) for name in names}


# {
# 責務: [score_metrics: compute a normalized weighted task objective]
# 処理: [invert leakage and memorization penalties, weight all axes, and return score evidence]
# 引数: [means: averaged metric axes, weights: task-specific preferences]
# 戻り値: [tuple[float, dict[str, float]]: score and human-readable axis values]
# }
def score_metrics(means: dict[str, float], weights: ScoreWeights) -> tuple[float, dict[str, float]]:
    values = dict(means)
    weighted = {
        name: getattr(weights, name) * (1 - value if name in {"leakage", "memorization"} else value)
        for name, value in values.items()
    }
    total = sum(vars(weights).values())
    score = sum(weighted.values()) / total
    return score, {**values, "weighted_score": score}


# {
# 責務: [score_weights_for_task: resolve built-in task-specific score priorities]
# 処理: [select balanced task weights or emphasize fidelity while preserving overfit penalties]
# 引数: [task: personalization objective, preset: balanced or fidelity priority profile]
# 戻り値: [ScoreWeights: weighted score configuration]
# エラー: [ValueError: task or preset is unsupported]
# }
def score_weights_for_task(
    task: ValidationTask, preset: ScorePreset = ScorePreset.BALANCED
) -> ScoreWeights:
    balanced = {
        ValidationTask.CHARACTER: ScoreWeights(1.0, 1.2, 0.8, 1.0, 1.0, 1.4, 1.2),
        ValidationTask.STYLE: ScoreWeights(1.0, 1.0, 0.9, 1.2, 0.8, 1.3, 1.0),
        ValidationTask.OBJECT: ScoreWeights(1.0, 1.2, 1.0, 1.0, 1.0, 1.3, 1.2),
        ValidationTask.MULTI_CONCEPT: ScoreWeights(1.1, 1.3, 0.8, 0.9, 1.1, 1.5, 1.3),
    }
    if task not in balanced:
        raise ValueError(f"unsupported validation task: {task}")
    weights = balanced[task]
    if preset is ScorePreset.BALANCED:
        return weights
    if preset is ScorePreset.FIDELITY:
        return ScoreWeights(
            weights.fidelity * 2,
            weights.controllability,
            weights.quality,
            weights.diversity,
            weights.base_preservation,
            weights.leakage,
            weights.memorization,
        )
    raise ValueError(f"unsupported scoring preset: {preset}")


# {
# 責務: [overfit_signals: compare one checkpoint against the previous validation]
# 処理: [detect multi-axis control loss, leakage, memorization, diversity, quality and base drift]
# 引数: [current: current normalized metrics, previous: previous checkpoint metrics, policy: signal threshold]
# 戻り値: [tuple[str, ...]: independent overfit signal descriptions]
# }
def overfit_signals(
    current: dict[str, float],
    previous: dict[str, float] | None,
    policy: EarlyStopPolicy,
) -> tuple[str, ...]:
    if previous is None:
        return ()
    threshold = policy.signal_threshold
    signals = []
    for key, text in (
        ("controllability", "controllability declined"),
        ("base_preservation", "base-model preservation declined"),
        ("diversity", "generation diversity collapsed"),
        ("quality", "image quality declined"),
    ):
        if previous[key] - current[key] >= threshold:
            signals.append(text)
    if current["leakage"] - previous["leakage"] >= threshold:
        signals.append("trigger-free concept leakage increased")
    if current["memorization"] - previous["memorization"] >= threshold:
        signals.append("training-image memorization similarity increased")
    if current["fidelity"] > previous["fidelity"] and len(signals) >= 1:
        signals.append("fidelity rose while another quality axis regressed")
    return tuple(signals)
