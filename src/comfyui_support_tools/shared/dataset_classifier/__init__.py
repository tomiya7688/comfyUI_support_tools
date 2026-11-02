"""Shared multi-axis dataset classification and extraction service."""

from .application import DatasetClassifierApplication, SidecarMetadataClassifier
from .clustering import ImageEmbeddingProvider, StyleEmbeddingClusterer
from .contracts import (
    AxisClassifier,
    ClassificationEvidence,
    ClassificationResult,
    DatasetQuery,
    QueryCondition,
    QueryGroup,
    TransferRecord,
)
from .query import matches_query, query_preset, validate_query

__all__ = [
    "AxisClassifier",
    "ClassificationEvidence",
    "ClassificationResult",
    "DatasetClassifierApplication",
    "DatasetQuery",
    "ImageEmbeddingProvider",
    "QueryCondition",
    "QueryGroup",
    "SidecarMetadataClassifier",
    "StyleEmbeddingClusterer",
    "TransferRecord",
    "matches_query",
    "query_preset",
    "validate_query",
]
