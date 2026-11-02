"""Coordinate deterministic checkpoint evaluation, scoring, stopping and rollback."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from .contracts import (
    CheckpointAssessment,
    CheckpointRef,
    EarlyStopPolicy,
    EvaluationContext,
    FixedConditions,
    ImageEvidence,
    ScorePreset,
    ScoreWeights,
    TrainingDoctorReport,
    TrainingTracePoint,
    ValidationPlan,
    ValidationSample,
)
from .scoring import overfit_signals, score_metrics, score_weights_for_task


# {
# 責務: [ValidationEvaluator: define a trainer-neutral image and quality evaluation bridge]
# フィールド: [none: implementation is supplied by a local generation/quality stack]
# 処理: [render the exact checkpoint/context pair and return measured normalized metrics]
# 引数: [checkpoint: selected model artifact, context: fixed prompt and inference conditions]
# 戻り値: [ImageEvidence: measured fidelity, control, quality, preservation, leakage, memorization, diversity and preview]
# }
class ValidationEvaluator(Protocol):
    # {
    # 責務: [evaluate: render one deterministic sample and return measured quality evidence]
    # 処理: [1: render one deterministic sample and return measured quality evidence]
    # 引数: [checkpoint: model artifact, context: prompt and generation settings]
    # 戻り値: [ImageEvidence: metrics and generated preview]
    # }

    def evaluate(self, checkpoint: CheckpointRef, context: EvaluationContext) -> ImageEvidence: ...


# {
# 責務: [TrainingDoctorApplication: select reliable LoRA checkpoints from held-out validation]
# フィールド: [evaluator: generation and image-quality bridge, stop_training: optional trainer control callback]
# 処理: [run fixed multi-seed prompt/strength/trigger sweeps, score quality dimensions, explain stop and retain best evidence]
# 引数: [evaluator: renderer plus image-quality metric provider, stop_training: optional early-stop request]
# 戻り値: [None: configured training doctor]
# }
class TrainingDoctorApplication:
    # {
    # 責務: [__init__: bind an evaluator and optional early-stop callback]
    # 処理: [1: bind an evaluator and optional early-stop callback]
    # 引数: [evaluator: generation and quality bridge, stop_training: trainer stop hook]
    # 戻り値: [None: application ready]
    # }

    def __init__(
        self, evaluator: ValidationEvaluator, stop_training: Callable[[str], None] | None = None
    ) -> None:
        self.evaluator = evaluator
        self.stop_training = stop_training

    # {
    # 責務: [evaluate_checkpoints: compare ordered checkpoints under identical inference conditions]
    # 処理: [validate inputs, run fixed scenario sweeps, select strength and trigger, track signals, and build a report]
    # 引数: [checkpoints: saved training checkpoints in step order, plan: fixed prompt matrix, strengths: inference scales, weights: task objective, policy: stop thresholds, trace: training diagnostics, score_preset: balanced or fidelity objective]
    # 戻り値: [TrainingDoctorReport: best/final checkpoint, recommendation, metrics, curves and stop reason]
    # エラー: [ValueError: checkpoints or sweep values are invalid or evaluation budget is exceeded]
    # }
    def evaluate_checkpoints(
        self,
        checkpoints: Sequence[CheckpointRef],
        plan: ValidationPlan,
        strengths: Sequence[float] = (0.4, 0.6, 0.8, 1.0, 1.2),
        weights: ScoreWeights | None = None,
        policy: EarlyStopPolicy | None = None,
        trace: Sequence[TrainingTracePoint] = (),
        score_preset: ScorePreset = ScorePreset.BALANCED,
    ) -> TrainingDoctorReport:
        ordered, scale_grid = self._validate_inputs(checkpoints, strengths, plan)
        objective = weights or score_weights_for_task(plan.task, score_preset)
        stop_policy = policy or EarlyStopPolicy()
        assessments: list[CheckpointAssessment] = []
        previous: dict[str, float] | None = None
        best_score = -math.inf
        stale_rounds = overfit_rounds = 0
        onset = None
        stop_reason = "all available checkpoints were evaluated"
        sample_budget = 100_000
        sample_count = (
            len(plan.scenarios)
            * len(plan.conditions.seeds)
            * len(plan.conditions.resolutions)
            * len(plan.conditions.inference_step_values)
        )
        if sample_count * len(scale_grid) * len(ordered) > sample_budget:
            raise ValueError("validation matrix exceeds the 100000 image evaluation budget")
        for checkpoint in ordered:
            samples = self._evaluate_checkpoint(checkpoint, plan, scale_grid)
            assessment = self._assess(checkpoint, samples, plan, objective, previous, stop_policy)
            assessments.append(assessment)
            means = assessment.score_breakdown
            assessment_signals = assessment.signals
            if len(assessment_signals) >= 2:
                overfit_rounds += 1
                onset = checkpoint.step if onset is None else onset
            else:
                overfit_rounds = 0
            if assessment.score >= best_score + stop_policy.minimum_improvement:
                best_score = assessment.score
                previous = means
                stale_rounds = 0
            else:
                stale_rounds += 1
            if overfit_rounds >= stop_policy.overfit_patience:
                stop_reason = self._overfit_stop_reason(assessment_signals, overfit_rounds)
            elif stale_rounds >= stop_policy.patience:
                stop_reason = (
                    f"validation score did not improve by {stop_policy.minimum_improvement:.3f} "
                    f"for {stale_rounds} consecutive checkpoints"
                )
            if stop_reason != "all available checkpoints were evaluated":
                if self.stop_training:
                    self.stop_training(stop_reason)
                break
        best = max(assessments, key=lambda result: result.score)
        selected_samples = best.samples
        leakage = best.score_breakdown["leakage"]
        return TrainingDoctorReport(
            best.checkpoint.path,
            assessments[-1].checkpoint.path,
            best.recommended_strength,
            best.recommended_trigger,
            best.score_breakdown,
            onset,
            leakage,
            best.score_breakdown["base_preservation"],
            selected_samples,
            tuple(sorted(trace, key=lambda point: point.step)),
            stop_reason,
            tuple(assessments),
            plan.recommended_tags,
            plan.task,
            score_preset,
        )

    # {
    # 責務: [_validate_inputs: reject ambiguous checkpoint and sweep requests]
    # 処理: [sort unique checkpoint steps, validate scales and estimate fixed generation count]
    # 引数: [checkpoints: requested saved artifacts, strengths: inference scale grid, plan: fixed validation matrix]
    # 戻り値: [tuple[tuple[CheckpointRef, ...], tuple[float, ...]]: stable ordered sweep]
    # }
    @staticmethod
    def _validate_inputs(
        checkpoints: Sequence[CheckpointRef],
        strengths: Sequence[float],
        plan: ValidationPlan,
    ) -> tuple[tuple[CheckpointRef, ...], tuple[float, ...]]:
        ordered = tuple(sorted(checkpoints, key=lambda checkpoint: checkpoint.step))
        if not ordered or len({item.step for item in ordered}) != len(ordered):
            raise ValueError("at least one checkpoint with a unique step is required")
        if any(not checkpoint.path.exists() for checkpoint in ordered):
            raise ValueError("every checkpoint path must exist before validation")
        grid = tuple(float(value) for value in strengths)
        if not grid or len(grid) > 32 or len(set(grid)) != len(grid):
            raise ValueError("LoRA strength grid must contain 1..32 unique values")
        if any(not math.isfinite(value) or not 0 <= value <= 2 for value in grid):
            raise ValueError("LoRA strengths must be finite and in 0..2")
        if len(plan.conditions.seeds) > 32 or len(plan.conditions.resolutions) > 8:
            raise ValueError("validation conditions exceed safe generation limits")
        return ordered, grid

    # {
    # 責務: [_evaluate_checkpoint: render every scenario at each strength and fixed condition]
    # 処理: [iterate trigger candidates, seeds and resolutions and reject malformed evaluator results]
    # 引数: [checkpoint: selected artifact, plan: deterministic validation plan, strengths: inference sweep]
    # 戻り値: [tuple[ValidationSample, ...]: complete measured generation evidence]
    # }
    def _evaluate_checkpoint(
        self, checkpoint: CheckpointRef, plan: ValidationPlan, strengths: tuple[float, ...]
    ) -> tuple[ValidationSample, ...]:
        result = []
        settings: FixedConditions = plan.conditions
        for strength in strengths:
            for scenario in plan.scenarios:
                for seed in settings.seeds:
                    for resolution in settings.resolutions:
                        for inference_steps in settings.inference_step_values:
                            context = EvaluationContext(
                                scenario,
                                seed,
                                settings.sampler,
                                inference_steps,
                                resolution,
                                strength,
                            )
                            evidence = self.evaluator.evaluate(checkpoint, context)
                            if not isinstance(evidence, ImageEvidence):
                                raise TypeError("validation evaluator must return ImageEvidence")
                            result.append(
                                ValidationSample(
                                    checkpoint,
                                    context,
                                    evidence.metrics,
                                    evidence.preview_path,
                                    evidence.sha256,
                                )
                            )
        return tuple(result)

    # {
    # 責務: [_assess: choose strength and trigger with the best balanced quality score]
    # 処理: [score each trigger/strength pair, compare prior axes, and retain selected samples]
    # 引数: [checkpoint: current artifact, samples: measured candidates, plan: shared conditions, weights: score weights, previous: prior validation axes, policy: signal threshold]
    # 戻り値: [CheckpointAssessment: selected candidate and explainable metrics]
    # }
    @staticmethod
    def _assess(
        checkpoint: CheckpointRef,
        samples: tuple[ValidationSample, ...],
        plan: ValidationPlan,
        weights: ScoreWeights,
        previous: dict[str, float] | None,
        policy: EarlyStopPolicy,
    ) -> CheckpointAssessment:
        candidates = plan.trigger_candidates or (plan.trigger,)
        ranked = []
        selected_samples = ()
        for trigger in candidates:
            trigger_rows = tuple(
                sample
                for sample in samples
                if (sample.context.scenario.trigger_variant or plan.trigger) == trigger
                or not sample.context.scenario.trigger_present
            )
            for strength in sorted({row.context.strength for row in trigger_rows}):
                rows = tuple(row for row in trigger_rows if row.context.strength == strength)
                means = _axis_means(rows)
                score, breakdown = score_metrics(means, weights)
                ranked.append((score, trigger, strength, breakdown, rows))
        if not ranked:
            raise ValueError("validation plan produced no trigger candidates")
        score, trigger, strength, breakdown, selected_samples = max(
            ranked, key=lambda item: item[0]
        )
        signals = overfit_signals(breakdown, previous, policy)
        return CheckpointAssessment(
            checkpoint, score, breakdown, strength, trigger, signals, selected_samples
        )

    # {
    # 責務: [_overfit_stop_reason: explain a persistent multi-signal early stop]
    # 処理: [list independent regression signals and required consecutive validations]
    # 引数: [signals: current overfit indicators, rounds: consecutive flagged validations]
    # 戻り値: [str: user-readable early-stop explanation]
    # }
    @staticmethod
    def _overfit_stop_reason(signals: tuple[str, ...], rounds: int) -> str:
        return (
            f"early stop after {rounds} consecutive multi-signal overfit validations: "
            + "; ".join(signals)
        )

    # {
    # 責務: [restore_best: ask the trainer integration to restore the selected checkpoint]
    # 処理: [verify the selected artifact still exists and invoke the explicit rollback callback]
    # 引数: [report: completed validation report, restore: trainer-specific checkpoint restore callback]
    # 戻り値: [None: callback performs the trainer-specific rollback]
    # エラー: [FileNotFoundError: selected checkpoint was removed after evaluation]
    # }
    @staticmethod
    def restore_best(report: TrainingDoctorReport, restore: Callable[[Path], None]) -> None:
        if not report.best_checkpoint.exists():
            raise FileNotFoundError(report.best_checkpoint)
        restore(report.best_checkpoint)

    # {
    # 責務: [publish_prompt_metadata: send strength and trigger recommendations to a prompt metadata consumer]
    # 処理: [export the stable additive payload through the consumer's save method]
    # 引数: [report: selected training result, save: metadata sink callback]
    # 戻り値: [None: consumer owns prompt metadata persistence]
    # }
    @staticmethod
    def publish_prompt_metadata(
        report: TrainingDoctorReport, save: Callable[[dict[str, object]], None]
    ) -> None:
        save(report.prompt_metadata())


# {
# 責務: [_axis_means: separate trigger-only and trigger-free quality observations]
# 処理: [measure fidelity/control from triggered prompts, preservation/leakage from absent prompts, and average supported dimensions]
# 引数: [samples: selected trigger and shared baseline validation rows]
# 戻り値: [dict[str, float]: one complete score-axis map]
# エラー: [ValueError: prompt plan lacks trigger or trigger-free scenarios]
# }
def _axis_means(samples: tuple[ValidationSample, ...]) -> dict[str, float]:
    trigger_rows = [row.metrics for row in samples if row.context.scenario.trigger_present]
    baseline_rows = [row.metrics for row in samples if not row.context.scenario.trigger_present]
    if not trigger_rows or not baseline_rows:
        raise ValueError("validation plan must include triggered and trigger-free scenarios")
    from statistics import fmean

    return {
        "fidelity": fmean(row.fidelity for row in trigger_rows),
        "controllability": fmean(row.controllability for row in trigger_rows),
        "quality": fmean(row.quality for row in trigger_rows),
        "diversity": fmean(row.diversity for row in trigger_rows),
        "memorization": fmean(row.memorization for row in trigger_rows),
        "base_preservation": fmean(row.base_preservation for row in baseline_rows),
        "leakage": fmean(row.leakage for row in baseline_rows),
    }
