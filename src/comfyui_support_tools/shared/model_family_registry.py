from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


# {
# 責務: [ ModelFamilyEvidence: detectorの結論とprovenanceを保持する ]
# フィールド: [ family: family ID, reason: 根拠, confidence: 未校正の一致強度, detector_id: provider ID, version: descriptor version ]
# 処理: []
# }
@dataclass(frozen=True)
class ModelFamilyEvidence:
    family: str
    reason: str
    confidence: float | None
    detector_id: str
    version: str

    # {
    # 責務: [ __post_init__: evidence identityとconfidence範囲を検証する ]
    # 処理: [ 1: 必須識別子を確認する, 2: confidence範囲を検証する ]
    # 引数: [ self: evidence instance ]
    # 戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.family or not self.detector_id or not self.version:
            raise ValueError("model-family evidence requires family, detector ID, and version")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("model-family evidence confidence must be between 0 and 1")


# {
# 責務: [ ModelFamilyDetector: evidence providerが実装するextension contract ]
# フィールド: []
# 処理: []
# }
class ModelFamilyDetector(Protocol):
    detector_id: str
    version: str
    applicable_kinds: frozenset[str]

    # {
    # 責務: [ detect: detector固有の証拠からfamily evidenceを返す ]
    # 処理: [ 1: model evidenceを評価する, 2: provenance付き結果を返す ]
    # 引数: [ self: detector, model_path: path hint, metadata: metadata hints, tensor_shapes: tensor shape hints ]
    # 戻り値: [ evidence: 検出結果 ]
    # }
    def detect(
        self,
        model_path: str | Path,
        metadata: Mapping[str, str] | None,
        tensor_shapes: Mapping[str, Sequence[int]] | None,
    ) -> Sequence[ModelFamilyEvidence]: ...


# {
# 責務: [ ModelFamilyDetectorRegistry: detectorを重複なく登録し適用する ]
# フィールド: [ _detectors: 登録順のdetector ]
# 処理: []
# }
class ModelFamilyDetectorRegistry:
    # {
    # 責務: [ __init__: 空のregistryを作る ]
    # 処理: [ 1: 登録先を初期化する ]
    # 引数: [ self: instance ]
    # 戻り値: []
    # }
    def __init__(self) -> None:
        self._detectors: list[ModelFamilyDetector] = []

    # {
    # 責務: [ register: detector IDを一意に保って登録する ]
    # 処理: [ 1: 重複IDを確認する, 2: detectorを登録する ]
    # 引数: [ self: instance, detector: 登録するprovider ]
    # 戻り値: []
    # }
    def register(self, detector: ModelFamilyDetector) -> None:
        if any(item.detector_id == detector.detector_id for item in self._detectors):
            raise ValueError(f"Duplicate model-family detector: {detector.detector_id}")
        self._detectors.append(detector)

    # {
    # 責務: [ detect: model kindに適用できるdetector evidenceを集める ]
    # 処理: [ 1: applicabilityを確認する, 2: evidenceを統合して返す ]
    # 引数: [ self: instance, model_path: model path, metadata: metadata, tensor_shapes: tensor shape, model_kind: model kind ]
    # 戻り値: [ evidence: detector結果列 ]
    # }
    def detect(
        self,
        model_path: str | Path,
        metadata: Mapping[str, str] | None,
        tensor_shapes: Mapping[str, Sequence[int]] | None,
        model_kind: str | None = None,
    ) -> tuple[ModelFamilyEvidence, ...]:
        return tuple(
            evidence
            for detector in self._detectors
            if model_kind is None
            or model_kind == "unknown"
            or not detector.applicable_kinds
            or model_kind in detector.applicable_kinds
            for evidence in detector.detect(model_path, metadata, tensor_shapes)
        )
