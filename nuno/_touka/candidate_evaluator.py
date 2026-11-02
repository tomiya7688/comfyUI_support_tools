from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Protocol

HEURISTIC_BASELINE_VERSION = "touka-heuristic-v1"


# {
# 責務: [ EvaluationResult: 候補評価のscoreと根拠metricを保持する ]
# フィールド: [ score: 合成score, breakdown: 指標別寄与, evaluator_id: evaluator識別子, version: version ]
# 処理: []
# }
@dataclass(frozen=True)
class EvaluationResult:
    score: float
    breakdown: Mapping[str, float]
    evaluator_id: str
    version: str


# {
# 責務: [ CandidateEvaluator: 候補evaluatorの交換可能な契約を定義する ]
# フィールド: []
# 処理: []
# 引数: []
# 戻り値: []
# }
class CandidateEvaluator(Protocol):
    # {
    # 責務: [ evaluate: featureとpresetから候補評価結果を生成する ]
    # 処理: [ 1: evaluator metricを算出する, 2: provenance付き結果を返す ]
    # 引数: [ self: evaluator, metrics: candidate feature, object_preset: preset名 ]
    # 戻り値: [ result: 評価結果 ]
    # }
    def evaluate(self, metrics: Mapping[str, float], object_preset: str) -> EvaluationResult: ...


# {
# 責務: [ HeuristicBaselineEvaluator: 既存Touka係数をversion付きbaselineとして適用する ]
# フィールド: [ PRESET_BONUSES: preset固有score係数 ]
# 処理: [ 1: metric寄与を算出する, 2: breakdownと合計を返す ]
# 引数: [ metrics: 候補feature, object_preset: 対象preset ]
# 戻り値: [ result: version/provenance付き評価結果 ]
# }
class HeuristicBaselineEvaluator:
    PRESET_BONUSES = {
        "clothing": ("area_ratio", 6.0),
        "cloth": ("temporal_shape", 5.0),
        "shirt": ("area_ratio", 6.5, "symmetry", 1.5),
        "bra": ("area_ratio", 5.8, "symmetry", 2.0),
        "panties": ("area_ratio", 5.8, "symmetry", 1.8),
        "skin": ("tracking_confidence", 3.0, "area_ratio", 3.0),
        "carpet": ("temporal_shape", 5.5, "area_ratio", 3.0),
        "ribbon": ("elongated_components", 0.5),
        "regular": ("components", 0.1),
        "solid": ("tracking_confidence", 4.0),
        "generic": (),
    }

    # {
    # 責務: [ evaluate: baseline heuristicでmetric breakdownを生成する ]
    # 処理: [ 1: metric係数を適用する, 2: preset寄与を追加する, 3: 合計する ]
    # 引数: [ metrics: 抽出済み候補metric, object_preset: preset名 ]
    # 戻り値: [ result: version付きscore内訳 ]
    # }
    def evaluate(self, metrics: Mapping[str, float], object_preset: str) -> EvaluationResult:
        if object_preset not in self.PRESET_BONUSES:
            raise ValueError(f"Unsupported Touka object preset: {object_preset}")
        coefficients = {
            "information_gain": 0.28,
            "edge_gain": 18.0,
            "shape_score": 1.0,
            "temporal_shape": 8.0,
            "tracking_confidence": 20.0,
            "flicker": -0.45,
            "camera_motion": -0.1,
            "clipping": -24.0,
            "deviation": -0.04,
            "halo": -4.0,
        }
        breakdown = {
            name: float(metrics.get(name, 0.0)) * coefficient
            for name, coefficient in coefficients.items()
        }
        breakdown["noise_penalty"] = -min(10.0, float(metrics.get("noise", 0.0)) / 500.0)
        preset = self.PRESET_BONUSES.get(object_preset, ())
        for index in range(0, len(preset), 2):
            feature, coefficient = preset[index : index + 2]
            breakdown["preset_bonus"] = breakdown.get("preset_bonus", 0.0) + (
                float(metrics.get(feature, 0.0)) * coefficient
            )
        return EvaluationResult(
            score=sum(breakdown.values()),
            breakdown=breakdown,
            evaluator_id="touka.heuristic_baseline",
            version=HEURISTIC_BASELINE_VERSION,
        )


CALIBRATED_LINEAR_VERSION = "touka-calibrated-linear-v1"


# {
# 責務: [CalibratedLinearEvaluator: validation labelsで校正したlinear evaluatorを保持する]
# フィールド: [weights: feature係数, intercept: bias, evaluator_id: stable ID, version: calibration version]
# 処理: [1: feature寄与とbiasを計算する 2: provenance付き結果を返す]
# 引数: [metrics: candidate features, object_preset: unused preset compatibility field]
# 戻り値: [EvaluationResult]
# }
@dataclass(frozen=True)
class CalibratedLinearEvaluator:
    weights: Mapping[str, float]
    intercept: float
    evaluator_id: str = "touka.calibrated.linear"
    version: str = CALIBRATED_LINEAR_VERSION

    # {
    # 責務: [evaluate: 校正済み係数で候補を採点する]
    # 処理: [1: 各feature寄与を算出する 2: 合計とprovenanceを返す]
    # 引数: [self: evaluator, metrics: candidate features, object_preset: unused preset]
    # 戻り値: [EvaluationResult]
    # }
    def evaluate(self, metrics: Mapping[str, float], object_preset: str) -> EvaluationResult:
        del object_preset
        breakdown = {
            name: float(metrics.get(name, 0.0)) * coefficient
            for name, coefficient in self.weights.items()
        }
        breakdown["intercept"] = self.intercept
        return EvaluationResult(
            sum(breakdown.values()),
            breakdown,
            self.evaluator_id,
            self.version,
        )


# {
# 責務: [_solve_linear_system: regularized normal equationをGaussian eliminationで解く]
# 処理: [1: 最大pivotを選ぶ 2: 行を消去する 3: coefficient vectorを返す]
# 引数: [matrix: square coefficient matrix, target: right-hand vector]
# 戻り値: [solution: linear coefficients]
# }
def _solve_linear_system(matrix: list[list[float]], target: list[float]) -> list[float]:
    size = len(target)
    augmented = [row[:] + [target[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("calibration data is numerically singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[row][-1] for row in range(size)]


# {
# 責務: [calibrate_linear_evaluator: labeled validation examplesからridge linear evaluatorをfitする]
# 処理: [1: 入力shapeとfinite値を検証する 2: normal equationを構築する 3: fitted evaluatorを返す]
# 引数: [features: candidate feature maps, ground_truth_quality: human quality labels, regularization: positive ridge strength]
# 戻り値: [CalibratedLinearEvaluator]
# }
def calibrate_linear_evaluator(
    features: list[Mapping[str, float]],
    ground_truth_quality: list[float],
    *,
    regularization: float = 1e-6,
    evaluator_id: str = "touka.calibrated.linear",
) -> CalibratedLinearEvaluator:
    if len(features) != len(ground_truth_quality) or len(features) < 2:
        raise ValueError("calibration requires at least two feature/quality pairs")
    if not evaluator_id.strip() or not isfinite(regularization) or regularization <= 0:
        raise ValueError("evaluator_id must be non-empty and regularization must be positive")
    names = tuple(sorted({name for item in features for name in item}))
    if not names:
        raise ValueError("calibration requires at least one feature")
    rows = [[float(item.get(name, 0.0)) for name in names] + [1.0] for item in features]
    labels = [float(value) for value in ground_truth_quality]
    if not all(isfinite(value) for row in rows for value in row) or not all(
        isfinite(value) for value in labels
    ):
        raise ValueError("calibration features and labels must be finite numbers")
    dimension = len(names) + 1
    matrix = [
        [
            sum(row[left] * row[right] for row in rows)
            + (regularization if left == right and left < len(names) else 0.0)
            for right in range(dimension)
        ]
        for left in range(dimension)
    ]
    target = [
        sum(row[index] * label for row, label in zip(rows, labels, strict=True))
        for index in range(dimension)
    ]
    coefficients = _solve_linear_system(matrix, target)
    return CalibratedLinearEvaluator(
        weights=dict(zip(names, coefficients[:-1], strict=True)),
        intercept=coefficients[-1],
        evaluator_id=evaluator_id,
    )
