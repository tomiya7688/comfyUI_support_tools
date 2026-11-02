"""Adapter-neutral dataset classification, query, and transfer contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


# {
# 責務: [ClassificationEvidence: preserve one classifier or metadata claim]
# フィールド: [axis, label, confidence, source, weight, priority]
# 処理: [support auditable multi-evidence score fusion and metadata precedence]
# }
@dataclass(frozen=True)
class ClassificationEvidence:
    axis: str
    label: str
    confidence: float
    source: str
    weight: float = 1.0
    priority: int = 0


# {
# 責務: [ClassificationResult: store labels, evidence, confidence and uncertainty per image]
# フィールド: [source, labels, confidence, evidence, alternates, disagreement, uncertainty, overrides]
# 処理: [unify manual review, query matching, and export handoff data]
# }
@dataclass(frozen=True)
class ClassificationResult:
    source: Path
    labels: tuple[tuple[str, tuple[str, ...]], ...]
    confidence: tuple[tuple[str, float], ...]
    evidence: tuple[ClassificationEvidence, ...]
    alternates: tuple[tuple[str, tuple[str, ...]], ...] = ()
    disagreement: tuple[tuple[str, float], ...] = ()
    uncertain_axes: tuple[str, ...] = ()
    manual_overrides: tuple[tuple[str, tuple[str, ...]], ...] = ()


# {
# 責務: [AxisClassifier: define one replaceable semantic or metadata adapter]
# フィールド: [classify callable]
# 処理: [allow tagger, VLM, scene, style, identity and provenance evidence plugins]
# }
class AxisClassifier(Protocol):
    # {
    # 責務: [classify: emit score-bearing labels for one image]
    # 処理: [return auditable label evidence without forcing top-one selection]
    # 引数: [image_path: source image file]
    # 戻り値: [tuple[ClassificationEvidence, ...]: candidate evidence]
    # }
    def classify(self, image_path: Path) -> tuple[ClassificationEvidence, ...]: ...


# {
# 責務: [QueryCondition: express one label/confidence predicate]
# フィールド: [axis, operator, value, min_confidence]
# 処理: [support equality, containment and set membership filters]
# }
@dataclass(frozen=True)
class QueryCondition:
    axis: str
    operator: str
    value: str | tuple[str, ...]
    min_confidence: float = 0.0


# {
# 責務: [QueryGroup: combine conditions with boolean logic]
# フィールド: [operator, children]
# 処理: [support nested AND / OR / NOT query trees]
# }
@dataclass(frozen=True)
class QueryGroup:
    operator: str
    children: tuple[QueryCondition | QueryGroup, ...]


# {
# 責務: [DatasetQuery: package a versioned dataset extraction query]
# フィールド: [root, expression, axes, action, preserve_relative]
# 処理: [replay and share dataset selections reproducibly]
# }
@dataclass(frozen=True)
class DatasetQuery:
    root: Path
    expression: QueryCondition | QueryGroup
    axes: tuple[str, ...] = ()
    action: str = "manifest"
    preserve_relative: bool = True


# {
# 責務: [TransferRecord: record planned or completed file transfer details]
# フィールド: [source, destination, action, labels, confidence, evidence]
# 処理: [provide reversible audit trail for copy/move/manifest-only jobs]
# }
@dataclass(frozen=True)
class TransferRecord:
    source: Path
    destination: Path | None
    action: str
    labels: tuple[tuple[str, tuple[str, ...]], ...]
    confidence: tuple[tuple[str, float], ...]
    evidence: tuple[ClassificationEvidence, ...]
    manual_overrides: tuple[tuple[str, tuple[str, ...]], ...] = ()
