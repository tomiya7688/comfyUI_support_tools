"""Explainable local features for hard-case clustering and sampling."""

from __future__ import annotations

import io
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from PIL import Image

from .contracts import HardCaseFeatures, HardCaseRecord


# {
#   責務: [HardCaseCluster: related feature/tag recordsとrepresentativeを表す]
#   フィールド: [cluster_id, record_ids, representative_record_id, feature_centroid, tags]
# }
@dataclass(frozen=True, slots=True)
class HardCaseCluster:
    cluster_id: str
    record_ids: tuple[str, ...]
    representative_record_id: str
    feature_centroid: tuple[float, ...]
    tags: tuple[str, ...]


# {
#   責務: [extract_hard_case_features: confidence mapとcandidate residualsからinterpretable featureを計算する]
#   処理: [derive low-confidence area and normalized disagreement without learned embeddings]
#   引数: [confidence_map_png: L-mode confidence image, candidate_scores: normalized raw candidate scores, reconstruction_residual: optional residual metric, temporal_disagreement: optional temporal metric, artifact_score: optional artifact metric, low_confidence_threshold: pixel cutoff]
#   戻り値: [HardCaseFeatures: normalized multi-axis descriptor]
# }
def extract_hard_case_features(
    confidence_map_png: bytes,
    candidate_scores: tuple[float, ...],
    reconstruction_residual: float = 0.0,
    temporal_disagreement: float = 0.0,
    artifact_score: float = 0.0,
    low_confidence_threshold: float = 0.45,
) -> HardCaseFeatures:
    _validate_fraction(reconstruction_residual, "reconstruction_residual")
    _validate_fraction(temporal_disagreement, "temporal_disagreement")
    _validate_fraction(artifact_score, "artifact_score")
    _validate_fraction(low_confidence_threshold, "low_confidence_threshold")
    if not candidate_scores:
        raise ValueError("candidate_scores must contain at least one value")
    for score in candidate_scores:
        _validate_fraction(score, "candidate_score")
    try:
        with Image.open(io.BytesIO(confidence_map_png)) as confidence_image:
            confidence_map = np.asarray(confidence_image.convert("L"), dtype=np.float32) / 255
    except (OSError, ValueError) as error:
        raise ValueError("confidence map must be a decodable image") from error
    disagreement = float(np.std(np.asarray(candidate_scores, dtype=np.float32)))
    return HardCaseFeatures(
        reconstruction_residual=float(reconstruction_residual),
        low_confidence_area_ratio=float(np.mean(confidence_map < low_confidence_threshold)),
        candidate_disagreement=min(disagreement, 1.0),
        temporal_disagreement=float(temporal_disagreement),
        artifact_score=float(artifact_score),
    )


# {
#   責務: [cluster_hard_cases: featuresとfailure tagsからrecordをgroup化する]
#   処理: [deterministic centroid threshold grouping with shared material/tag compatibility]
#   引数: [records: local failure examples, radius: normalized centroid distance cutoff]
#   戻り値: [tuple[HardCaseCluster, ...]: stable clusters with representative cases]
# }
def cluster_hard_cases(
    records: Iterable[HardCaseRecord], radius: float = 0.18
) -> tuple[HardCaseCluster, ...]:
    _validate_fraction(radius, "radius")
    ordered = tuple(sorted(records, key=lambda record: record.record_id))
    feature_vectors = {record.record_id: _feature_vector(record.features) for record in ordered}
    groups: list[list[HardCaseRecord]] = []
    centroids: list[np.ndarray] = []
    for record in ordered:
        vector = np.asarray(feature_vectors[record.record_id], dtype=np.float32)
        compatible = [
            index
            for index, members in enumerate(groups)
            if _compatible(record, members[0])
            and float(np.linalg.norm(vector - centroids[index]) / math.sqrt(len(vector))) <= radius
        ]
        if compatible:
            index = compatible[0]
            groups[index].append(record)
            centroids[index] = np.mean(
                [feature_vectors[member.record_id] for member in groups[index]], axis=0
            )
        else:
            groups.append([record])
            centroids.append(vector)
    clusters = []
    for members, centroid in zip(groups, centroids, strict=True):
        representative = min(
            members,
            key=lambda record: float(
                np.linalg.norm(np.asarray(feature_vectors[record.record_id]) - centroid)
            ),
        )
        tags = tuple(
            sorted({tag for record in members for tag in (*record.failure_tags, record.material)})
        )
        clusters.append(
            HardCaseCluster(
                f"hard-case-cluster-{len(clusters) + 1:04d}",
                tuple(record.record_id for record in members),
                representative.record_id,
                tuple(float(value) for value in centroid),
                tags,
            )
        )
    return tuple(clusters)


# {
#   責務: [select_active_learning_samples: rarity / disagreement / calibration riskからtraining examplesをrankする]
#   処理: [prioritize high-confidence rejection, candidate disagreement, rare materials/tags and hard features]
#   引数: [records: local history, limit: maximum selected cases]
#   戻り値: [tuple[HardCaseRecord, ...]: stable active-learning sample]
# }
def select_active_learning_samples(
    records: Iterable[HardCaseRecord], limit: int
) -> tuple[HardCaseRecord, ...]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    cases = tuple(records)
    counts = Counter(token for record in cases for token in (record.material, *record.failure_tags))
    ranked = sorted(
        cases,
        key=lambda record: (
            -_active_learning_score(record, counts),
            record.record_id,
        ),
    )
    return tuple(ranked[:limit])


# {
#   責務: [_active_learning_score: record hardness and rarityをsingle ranking scoreにする]
#   処理: [combine confidence, disagreement, residual, artifact, rare tags and explicit rejection]
#   引数: [record: hard-case example, frequencies: observed material/tag counts]
#   戻り値: [float: sortable priority]
# }
def _active_learning_score(record: HardCaseRecord, frequencies: Counter[str]) -> float:
    features = record.features
    selected = next(
        (item for item in record.candidates if item.candidate_id == record.selected_candidate), None
    )
    high_confidence_failure = bool(
        record.feedback_received
        and selected is not None
        and selected.confidence >= 0.8
        and (
            selected.candidate_id in record.rejected_candidates
            or (
                record.user_preferred_candidate
                and selected.candidate_id != record.user_preferred_candidate
            )
        )
    )
    tokens = (record.material, *record.failure_tags)
    rarity = sum(1 / math.sqrt(frequencies[token]) for token in tokens if token)
    rarity = min(rarity / max(len(tokens), 1), 1.0)
    return (
        0.18 * features.reconstruction_residual
        + 0.17 * features.low_confidence_area_ratio
        + 0.20 * features.candidate_disagreement
        + 0.12 * features.temporal_disagreement
        + 0.13 * features.artifact_score
        + 0.12 * rarity
        + 0.30 * float(high_confidence_failure)
    )


# {
#   責務: [_compatible: recordsが同じfailure clusterに属する可能性を判定する]
#   処理: [require matching material or at least one shared failure tag]
#   引数: [left: new record, right: cluster representative]
#   戻り値: [bool: semantic grouping is compatible]
# }
def _compatible(left: HardCaseRecord, right: HardCaseRecord) -> bool:
    return left.material == right.material or bool(set(left.failure_tags) & set(right.failure_tags))


# {
#   責務: [_feature_vector: typed hardness metricsをstable numeric vectorへ変換する]
#   処理: [retain a fixed feature order for clustering and centroid selection]
#   引数: [features: interpretable hard-case descriptor]
#   戻り値: [tuple[float, ...]: normalized feature vector]
# }
def _feature_vector(features: HardCaseFeatures) -> tuple[float, ...]:
    return (
        features.reconstruction_residual,
        features.low_confidence_area_ratio,
        features.candidate_disagreement,
        features.temporal_disagreement,
        features.artifact_score,
    )


# {
#   責務: [_validate_fraction: normalized feature inputをvalidateする]
#   処理: [reject bool, non-number, NaN, infinity and out-of-range values]
#   引数: [value: scalar, name: field name]
#   戻り値: []
# }
def _validate_fraction(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (float, int))
        or not math.isfinite(value)
        or not 0 <= value <= 1
    ):
        raise ValueError(f"{name} must be finite and between zero and one")
