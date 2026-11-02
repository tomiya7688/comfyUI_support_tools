"""Deterministic style-embedding cluster adapter for external feature models."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol

from .contracts import ClassificationEvidence


# {
# 責務: [ImageEmbeddingProvider: define a replaceable visual embedding backend]
# フィールド: [embed callable]
# 処理: [allow CLIP/style models to supply feature vectors without bundling weights]
# }
class ImageEmbeddingProvider(Protocol):
    # {
    # 責務: [embed: extract one finite feature vector for an image]
    # 処理: [normalize visual features outside dataset clustering]
    # 引数: [image_path: source image]
    # 戻り値: [tuple[float, ...]: embedding vector]
    # }
    def embed(self, image_path: Path) -> tuple[float, ...]: ...


# {
# 責務: [StyleEmbeddingClusterer: fit and reuse deterministic style clusters]
# フィールド: [provider, threshold, centroids, image assignments]
# 処理: [greedy cosine clustering with stable path ordering and uncertainty fallback]
# }
class StyleEmbeddingClusterer:
    # {
    # 責務: [__init__: configure embedding provider and similarity threshold]
    # 処理: [initialize empty cluster centroids]
    # 引数: [provider: visual embedding backend, similarity_threshold: cluster acceptance cosine]
    # 戻り値: [None: initialized clusterer]
    # }
    def __init__(self, provider: ImageEmbeddingProvider, similarity_threshold=0.82):
        if not 0 < similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be within (0, 1]")
        self.provider = provider
        self.similarity_threshold = similarity_threshold
        self.centroids = []
        self.assignments = {}
        self.dimensions = None

    # {
    # 責務: [version: expose provider and threshold identity for persistent cache invalidation]
    # 処理: [combine embedding provider version with the clustering cutoff]
    # 引数: [None: reads current provider configuration]
    # 戻り値: [str: stable cluster adapter version]
    # }
    @property
    def version(self):
        provider_type = type(self.provider)
        return f"{provider_type.__module__}.{provider_type.__qualname__}:{getattr(self.provider, 'version', '')}:{self.similarity_threshold}"

    # {
    # 責務: [fit: cluster all dataset images using cached embeddings]
    # 処理: [sort paths, assign by cosine threshold, and update normalized centroids]
    # 引数: [image_paths: style dataset paths]
    # 戻り値: [dict[Path, ClassificationEvidence]: stable cluster evidence per path]
    # }
    def fit(self, image_paths):
        self.centroids = []
        self.assignments = {}
        self.dimensions = None
        for image_path in sorted(
            (Path(path).resolve(strict=True) for path in image_paths), key=str
        ):
            vector = self._embedding(image_path)
            best_index, similarity = self._nearest(vector)
            if best_index is None or similarity < self.similarity_threshold:
                self.centroids.append((vector, 1))
                best_index = len(self.centroids) - 1
                similarity = 1.0
            else:
                centroid, count = self.centroids[best_index]
                updated = tuple(
                    (left * count + right) / (count + 1)
                    for left, right in zip(centroid, vector, strict=True)
                )
                self.centroids[best_index] = (_normalize(updated), count + 1)
            self.assignments[image_path] = self._evidence(best_index, similarity)
        return dict(self.assignments)

    # {
    # 責務: [classify: emit fitted or nearest style-cluster evidence]
    # 処理: [reuse fitted assignment or compute one nearest-centroid similarity]
    # 引数: [image_path: image to place into a style cluster]
    # 戻り値: [tuple[ClassificationEvidence, ...]: one style cluster claim]
    # }
    def classify(self, image_path):
        path = Path(image_path).resolve(strict=True)
        if path in self.assignments:
            return (self.assignments[path],)
        if not self.centroids:
            return ()
        index, similarity = self._nearest(self._embedding(path))
        label = self._evidence(index, similarity).label
        if similarity < self.similarity_threshold:
            label = "style_unknown"
        return (ClassificationEvidence("style", label, max(0.0, similarity), "style_embedding"),)

    # {
    # 責務: [_embedding: validate and normalize one external feature vector]
    # 処理: [reject non-finite, empty, zero-norm, or inconsistent dimension outputs]
    # 引数: [image_path: source image]
    # 戻り値: [tuple[float, ...]: normalized embedding]
    # }
    def _embedding(self, image_path):
        vector = self.provider.embed(image_path)
        if not isinstance(vector, (tuple, list)) or not vector:
            raise ValueError("embedding provider must return a non-empty numeric vector")
        if self.dimensions is None:
            self.dimensions = len(vector)
        if len(vector) != self.dimensions or any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in vector
        ):
            raise ValueError("embedding vector dimensions or values are invalid")
        return _normalize(tuple(float(value) for value in vector))

    # {
    # 責務: [_nearest: find the closest existing normalized style centroid]
    # 処理: [use cosine dot product with stable tie breaking]
    # 引数: [vector: normalized feature vector]
    # 戻り値: [tuple[int | None, float]: cluster index and similarity]
    # }
    def _nearest(self, vector):
        if not self.centroids:
            return None, 0.0
        scored = [
            (sum(left * right for left, right in zip(vector, centroid, strict=True)), index)
            for index, (centroid, _count) in enumerate(self.centroids)
        ]
        score, index = max(scored, key=lambda item: (item[0], -item[1]))
        return index, score

    # {
    # 責務: [_evidence: create the canonical label for one style cluster]
    # 処理: [format stable one-based cluster IDs]
    # 引数: [index: zero-based centroid index, confidence: cosine similarity]
    # 戻り値: [ClassificationEvidence: style label evidence]
    # }
    @staticmethod
    def _evidence(index, confidence):
        return ClassificationEvidence(
            "style", f"style_cluster_{index + 1:03d}", max(0.0, confidence), "style_embedding"
        )


# {
# 責務: [_normalize: convert a feature vector to unit length]
# 処理: [reject zero vectors and preserve tuple immutability]
# 引数: [vector: numeric feature tuple]
# 戻り値: [tuple[float, ...]: unit vector]
# }
def _normalize(vector):
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        raise ValueError("embedding vector must have non-zero magnitude")
    return tuple(value / norm for value in vector)
