from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
