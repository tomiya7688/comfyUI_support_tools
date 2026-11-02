"""Local feedback, hard-case mining, calibration, and regression tools."""

from .calibration import ConfidenceCalibrationReport, ReliabilityBin, calibrate_confidence
from .contracts import CandidateEvidence, HardCaseFeatures, HardCaseRecord
from .features import (
    HardCaseCluster,
    cluster_hard_cases,
    extract_hard_case_features,
    select_active_learning_samples,
)
from .regression import (
    HardCaseEvaluator,
    RegressionRunReport,
    compare_model_configs,
    export_active_learning_manifest,
    run_regression_set,
)
from .store import HardCaseStore

__all__ = [
    "CandidateEvidence",
    "ConfidenceCalibrationReport",
    "HardCaseCluster",
    "HardCaseEvaluator",
    "HardCaseFeatures",
    "HardCaseRecord",
    "HardCaseStore",
    "ReliabilityBin",
    "RegressionRunReport",
    "calibrate_confidence",
    "cluster_hard_cases",
    "compare_model_configs",
    "export_active_learning_manifest",
    "extract_hard_case_features",
    "run_regression_set",
    "select_active_learning_samples",
]
