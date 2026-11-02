"""Trainer-neutral dataset curation, caption, split, and export contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


# {
# 責務: [CuratorTask: select task-aware caption and coverage behavior]
# フィールド: [CHARACTER, CLOTHING, STYLE, OBJECT, POSE, CONCEPT]
# 処理: [provide stable serialized training intent identifiers]
# }
class CuratorTask(str, Enum):
    CHARACTER = "character"
    CLOTHING = "clothing"
    STYLE = "style"
    OBJECT = "object"
    POSE = "pose"
    CONCEPT = "concept"


# {
# 責務: [CaptionPolicy: choose a reproducible trainer caption variant]
# フィールド: [FULL_TAGS, VARIABLE_TAGS, SHORT, LONG, HYBRID]
# 処理: [provide stable caption selection policies]
# }
class CaptionPolicy(str, Enum):
    FULL_TAGS = "full_tags"
    VARIABLE_TAGS = "variable_tags"
    SHORT = "short"
    LONG = "long"
    HYBRID = "hybrid"


# {
# 責務: [CropPolicy: declare how the trainer may crop source images]
# フィールド: [PRESERVE, FACE_AWARE, SUBJECT_AWARE, RANDOM, MULTI_CROP]
# 処理: [retain crop intent without silently altering source pixels]
# }
class CropPolicy(str, Enum):
    PRESERVE = "preserve"
    FACE_AWARE = "face_aware"
    SUBJECT_AWARE = "subject_aware"
    RANDOM = "random"
    MULTI_CROP = "multi_crop"


# {
# 責務: [SourceKind: distinguish real and generated training samples]
# フィールド: [REAL, SYNTHETIC, UNKNOWN]
# 処理: [retain source provenance in manifests and fingerprints]
# }
class SourceKind(str, Enum):
    REAL = "real"
    SYNTHETIC = "synthetic"
    UNKNOWN = "unknown"


# {
# 責務: [OutlierClass: classify a reviewable sample concern]
# フィールド: [LIKELY_BAD, UNUSUAL_USEFUL, CONCEPT_MISMATCH, UNCERTAIN, NONE]
# 処理: [describe evidence without deleting or excluding an image automatically]
# }
class OutlierClass(str, Enum):
    LIKELY_BAD = "likely_bad"
    UNUSUAL_USEFUL = "unusual_but_useful"
    CONCEPT_MISMATCH = "concept_mismatch"
    UNCERTAIN = "uncertain"
    NONE = "none"


# {
# 責務: [SampleAction: store the explicit user decision for one sample]
# フィールド: [KEEP, LOW_WEIGHT, EXCLUDE]
# 処理: [represent reversible curation choices; no automatic file deletion]
# }
class SampleAction(str, Enum):
    KEEP = "keep"
    LOW_WEIGHT = "low_weight"
    EXCLUDE = "exclude"


# {
# 責務: [CharacterRegistryEvidence: carry accepted character/outfit evidence]
# フィールド: [identity, outfit, variable_attributes, accepted_traits, rejected_traits]
# 処理: [prefer user-confirmed traits and preserve outfit variability for caption ownership]
# 引数: [identity: identity labels, outfit: per-image outfit assignment, variable_attributes: confirmed variation, accepted_traits: approved traits, rejected_traits: rejected traits]
# 戻り値: [None: immutable registry evidence]
# }
@dataclass(frozen=True)
class CharacterRegistryEvidence:
    identity: tuple[str, ...] = ()
    outfit: tuple[str, ...] = ()
    variable_attributes: tuple[str, ...] = ()
    accepted_traits: tuple[str, ...] = ()
    rejected_traits: tuple[str, ...] = ()


# {
# 責務: [DatasetSampleInput: supply per-image metadata without requiring a specific tagger]
# フィールド: [image_path, raw_tags, attributes, short_caption, long_caption, negative_tags, confidence, source, source_kind, provenance, concept_match, registry]
# 処理: [preserve classifier outputs, user evidence, and real/synthetic provenance]
# 引数: [sample fields: image path, labels, caption variants, confidence, source and optional Character Registry evidence]
# 戻り値: [None: immutable inventory input]
# }
@dataclass(frozen=True)
class DatasetSampleInput:
    image_path: Path
    raw_tags: tuple[str, ...] = ()
    attributes: tuple[tuple[str, tuple[str, ...]], ...] = ()
    short_caption: str = ""
    long_caption: str = ""
    negative_tags: tuple[str, ...] = ()
    confidence: float = 0.0
    source: str = "manual"
    source_kind: SourceKind = SourceKind.UNKNOWN
    provenance: str = ""
    concept_match: bool | None = None
    registry: CharacterRegistryEvidence | None = None

    # {
    # 責務: [DatasetSampleInput.__post_init__: validate caption and confidence evidence]
    # 処理: [1: reject empty image paths and invalid confidence values]
    # 引数: [self: dataset sample input]
    # 戻り値: [None: validated input or ValueError]
    # }
    def __post_init__(self) -> None:
        if (
            not str(self.image_path)
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("sample image path and confidence must be valid")
        if self.concept_match is not None and not isinstance(self.concept_match, bool):
            raise ValueError("sample concept match must be boolean or unknown")
        if any(
            not axis.strip() or any(not label.strip() for label in labels)
            for axis, labels in self.attributes
        ):
            raise ValueError("sample attributes require nonempty axes and labels")


# {
# 責務: [SampleOverride: record user-reviewed decisions for one sample]
# フィールド: [image_path, action, weight, split, absorb_tags, variable_tags, outlier_class]
# 処理: [apply explicit keep/low-weight/exclude, split-group and caption ownership corrections]
# 引数: [image_path: stable source path, action: reviewed sample action, weight: optional bounded importance, split: optional train/validation group assignment, absorb_tags: task concept tags, variable_tags: caption-owned variation, outlier_class: corrected review category]
# 戻り値: [None: immutable user override]
# }
@dataclass(frozen=True)
class SampleOverride:
    image_path: Path
    action: SampleAction | None = None
    weight: float | None = None
    split: str | None = None
    absorb_tags: tuple[str, ...] = ()
    variable_tags: tuple[str, ...] = ()
    outlier_class: OutlierClass | None = None

    # {
    # 責務: [SampleOverride.__post_init__: validate explicit split decisions]
    # 処理: [reject unsupported manual split names]
    # 引数: [self: sample override]
    # 戻り値: [None: valid override or ValueError]
    # }
    def __post_init__(self) -> None:
        if self.split not in {None, "train", "validation"}:
            raise ValueError("manual split must be train, validation, or Auto")


# {
# 責務: [CuratorConfig: configure repeatable task-aware curation]
# フィールド: [task, base_family, caption_policy, crop_policy, validation_ratio, seed, duplicate_threshold, maximum_weight, required_coverage, fixed_clothing]
# 処理: [bound split, duplicate, and sample-weight policy]
# 引数: [config values: target task/model, caption/crop policy, validation ratio, split seed, near-duplicate threshold, max sample weight and coverage requirements]
# 戻り値: [None: validated immutable curation config]
# }
@dataclass(frozen=True)
class CuratorConfig:
    task: CuratorTask
    base_family: str = "unknown"
    caption_policy: CaptionPolicy = CaptionPolicy.HYBRID
    crop_policy: CropPolicy = CropPolicy.PRESERVE
    validation_ratio: float = 0.2
    seed: int = 1729
    duplicate_hamming_threshold: int = 5
    maximum_weight: float = 3.0
    required_coverage: tuple[tuple[str, tuple[str, ...]], ...] = ()
    fixed_clothing: bool = False

    # {
    # 責務: [CuratorConfig.__post_init__: validate deterministic curation limits]
    # 処理: [1: check ratio, perceptual threshold, and bounded weight maximum]
    # 引数: [self: curation configuration]
    # 戻り値: [None: validated configuration or ValueError]
    # }
    def __post_init__(self) -> None:
        if not 0 < self.validation_ratio < 0.5:
            raise ValueError("validation ratio must be in (0, 0.5)")
        if not 0 <= self.duplicate_hamming_threshold <= 16:
            raise ValueError("perceptual duplicate threshold must be in 0..16")
        if not 1 <= self.maximum_weight <= 8:
            raise ValueError("maximum sample weight must be in 1..8")
        if not isinstance(self.seed, int):
            raise ValueError("split seed must be an integer")


# {
# 責務: [CaptionSet: preserve source captions and independently selectable caption variants]
# フィールド: [raw_tags, normalized_tags, short_caption, long_caption, concept_caption, trainer_caption, negative_tags, confidence, source, absorb_tags, variable_tags]
# 処理: [retain caption ownership and confidence provenance for reproducible training]
# 引数: [caption values: tag variants, task-owned/variable tags, confidence and source]
# 戻り値: [None: immutable caption set]
# }
@dataclass(frozen=True)
class CaptionSet:
    raw_tags: tuple[str, ...]
    normalized_tags: tuple[str, ...]
    short_caption: str
    long_caption: str
    concept_caption: str
    trainer_caption: str
    negative_tags: tuple[str, ...]
    confidence: float
    source: str
    absorb_tags: tuple[str, ...]
    variable_tags: tuple[str, ...]


# {
# 責務: [ImageFeatures: record measured image metadata and optional vision evidence]
# フィールド: [width, height, sha256, perceptual_hash, blur_score, compression_score, crop_quality, face_visibility, body_visibility, concept_match]
# 処理: [retain measurable values separately from unknown classifier evidence]
# 引数: [feature values: dimensions, fingerprints, quality metrics and optional face/body scores]
# 戻り値: [None: immutable image feature record]
# }
@dataclass(frozen=True)
class ImageFeatures:
    width: int
    height: int
    sha256: str
    perceptual_hash: str
    blur_score: float
    compression_score: float
    crop_quality: float
    face_visibility: float | None = None
    body_visibility: float | None = None
    concept_match: bool | None = None


# {
# 責務: [CuratedSample: store one reviewable image and trainer assignment]
# フィールド: [image_path, image_id, features, captions, attributes, duplicate_group, duplicate_kind, outlier_class, action, sample_weight, split, crop_policy, source_kind, provenance]
# 処理: [make every automatic decision auditable and overridable]
# 引数: [sample values: inventory evidence, captions, duplicate grouping, review state and split]
# 戻り値: [None: immutable curated image]
# }
@dataclass(frozen=True)
class CuratedSample:
    image_path: Path
    image_id: str
    features: ImageFeatures
    captions: CaptionSet
    attributes: tuple[tuple[str, tuple[str, ...]], ...]
    duplicate_group: str
    duplicate_kind: str
    outlier_class: OutlierClass
    action: SampleAction
    sample_weight: float
    split: str
    crop_policy: CropPolicy
    source_kind: SourceKind
    provenance: str


# {
# 責務: [CoverageCell: report observed versus required task attributes]
# フィールド: [axis, label, count, required, missing]
# 処理: [expose rare and missing pose/background/clothing/viewpoint coverage]
# 引数: [cell values: normalized attribute tally]
# 戻り値: [None: immutable coverage row]
# }
@dataclass(frozen=True)
class CoverageCell:
    axis: str
    label: str
    count: int
    required: bool
    missing: bool


# {
# 責務: [DatasetAnalysis: provide reproducible curation decisions and coverage evidence]
# フィールド: [task, base_family, samples, coverage, missing_coverage, duplicate_groups, fingerprint, warnings]
# 処理: [summarize dataset selection, quality, split, captions and provenance]
# 引数: [analysis values: curated images, coverage grid, fingerprint and review warnings]
# 戻り値: [None: immutable analysis result]
# }
@dataclass(frozen=True)
class DatasetAnalysis:
    task: CuratorTask
    base_family: str
    samples: tuple[CuratedSample, ...]
    coverage: tuple[CoverageCell, ...]
    missing_coverage: tuple[CoverageCell, ...]
    duplicate_groups: tuple[tuple[str, tuple[Path, ...]], ...]
    fingerprint: str
    warnings: tuple[str, ...]
    regularization_images: tuple[tuple[Path, str], ...] = ()


# {
# 責務: [ImageEvidenceProvider: define optional face/body and concept classification]
# フィールド: [analyze callable]
# 処理: [return evidence or None when visibility cannot be measured]
# 引数: [image_path: local source image]
# 戻り値: [tuple[float | None, float | None, bool | None]: face visibility, body visibility, task concept match]
# }
class ImageEvidenceProvider(Protocol):
    # {
    # 責務: [analyze: measure optional semantic visibility evidence]
    # 処理: [run an injected vision/metadata classifier without inventing unknown labels]
    # 引数: [image_path: local source image]
    # 戻り値: [tuple[float | None, float | None, bool | None]: face, body and concept match evidence]
    # }
    def analyze(self, image_path: Path) -> tuple[float | None, float | None, bool | None]: ...


# {
# 責務: [EmbeddingSimilarityProvider: define an optional perceptual-near-duplicate adapter]
# フィールド: [similarity callable]
# 処理: [compare candidate image embeddings only when supplied by a local model]
# 引数: [first: source image, second: candidate image]
# 戻り値: [float: cosine-like similarity in 0..1]
# }
class EmbeddingSimilarityProvider(Protocol):
    # {
    # 責務: [similarity: measure local visual similarity]
    # 処理: [compare embeddings for duplicate grouping, without network access]
    # 引数: [first: source image, second: candidate image]
    # 戻り値: [float: visual similarity from 0 to 1]
    # }
    def similarity(self, first: Path, second: Path) -> float: ...


# {
# 責務: [CaptionPolicyProbe: bridge optional #55 micro-training caption comparisons]
# フィールド: [compare callable]
# 処理: [compare candidate caption policies without owning trainer setup]
# 引数: [analysis: curated dataset, policies: named caption variants]
# 戻り値: [tuple[tuple[str, float], ...]: held-out quality scores]
# }
class CaptionPolicyProbe(Protocol):
    # {
    # 責務: [compare: measure candidate caption policies on a trainer smoke run]
    # 処理: [run bounded #55 probe comparison using the caller's trainer bridge]
    # 引数: [analysis: dataset analysis, candidates: caption policy names and captions]
    # 戻り値: [tuple[tuple[str, float], ...]: normalized policy scores]
    # }
    def compare(
        self, analysis: DatasetAnalysis, candidates: tuple[tuple[str, tuple[str, ...]], ...]
    ) -> tuple[tuple[str, float], ...]: ...
