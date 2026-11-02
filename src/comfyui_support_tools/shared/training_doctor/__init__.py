"""Training Doctor contracts and trainer-neutral checkpoint quality workflow."""

from .application import TrainingDoctorApplication, ValidationEvaluator
from .contracts import (
    CheckpointAssessment,
    CheckpointRef,
    EarlyStopPolicy,
    EvaluationContext,
    FixedConditions,
    ImageEvidence,
    ImageMetrics,
    PromptScenario,
    ScorePreset,
    ScoreWeights,
    TrainingDoctorReport,
    TrainingTracePoint,
    ValidationPlan,
    ValidationSample,
    ValidationTask,
)
from .io import load_report, save_report
from .matrix import fixed_validation_plan
from .scoring import metric_means, overfit_signals, score_metrics, score_weights_for_task

__all__ = [
    "CheckpointAssessment",
    "CheckpointRef",
    "EarlyStopPolicy",
    "EvaluationContext",
    "FixedConditions",
    "ImageEvidence",
    "ImageMetrics",
    "PromptScenario",
    "ScorePreset",
    "ScoreWeights",
    "TrainingDoctorApplication",
    "TrainingDoctorReport",
    "TrainingTracePoint",
    "ValidationEvaluator",
    "ValidationPlan",
    "ValidationSample",
    "ValidationTask",
    "fixed_validation_plan",
    "load_report",
    "metric_means",
    "overfit_signals",
    "save_report",
    "score_metrics",
    "score_weights_for_task",
]
