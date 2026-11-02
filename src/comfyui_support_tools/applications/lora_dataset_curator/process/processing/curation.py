"""Application service for deterministic, trainer-neutral dataset curation."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from comfyui_support_tools.shared.contracts.dataset_curator import (
    CaptionPolicyProbe,
    CaptionSet,
    CoverageCell,
    CuratedSample,
    CuratorConfig,
    DatasetAnalysis,
    DatasetSampleInput,
    EmbeddingSimilarityProvider,
    ImageEvidenceProvider,
    ImageFeatures,
    OutlierClass,
    SampleAction,
    SampleOverride,
    SourceKind,
)

from .captions import build_captions, category_for_tag
from .image_analysis import IMAGE_EXTENSIONS, inspect_image
from .split import group_duplicates, sample_weights, split_by_duplicate_group

MAX_DATASET_IMAGES = 20_000
MAX_SIDECAR_BYTES = 64 * 1024
_DEFAULT_COVERAGE = {
    "character": {
        "pose": ("standing", "sitting"),
        "viewpoint": ("front_view", "side_view"),
        "expression": ("smile", "neutral_expression"),
        "background": ("indoor", "outdoor"),
        "clothing": ("dress", "coat", "uniform", "armor"),
    },
    "clothing": {
        "pose": ("standing", "sitting"),
        "viewpoint": ("front_view", "side_view"),
        "background": ("indoor", "outdoor"),
        "clothing": ("dress", "coat", "uniform", "armor"),
    },
    "style": {
        "subject": ("character", "object", "landscape"),
        "style": ("anime", "watercolor"),
        "composition": ("portrait", "landscape"),
        "lighting": ("soft_light", "sunlight"),
    },
    "object": {
        "viewpoint": ("front_view", "side_view"),
        "background": ("indoor", "outdoor"),
        "composition": ("close_up", "wide_shot"),
    },
    "pose": {"pose": ("standing", "sitting", "walking"), "viewpoint": ("front_view", "side_view")},
    "concept": {"pose": ("standing", "sitting"), "background": ("indoor", "outdoor")},
}


# {
# 責務: [_safe_child: validate an image or metadata path below a dataset root]
# 処理: [resolve strictly, reject symlinks, and require containment within the resolved root]
# 引数: [root: dataset directory, candidate: requested child path]
# 戻り値: [Path: canonical local file path]
# エラー: [ValueError: path is missing, linked, or outside the dataset]
# }
def _safe_child(root: Path, candidate: Path) -> Path:
    path = candidate if candidate.is_absolute() else root / candidate
    current = path
    while current != root and current != current.parent:
        if current.is_symlink():
            raise ValueError("dataset paths cannot traverse symbolic links")
        current = current.parent
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("dataset paths must stay inside the dataset root")
    return resolved


# {
# 責務: [_read_sidecar: read a bounded caption file adjacent to an image]
# 処理: [prefer txt then caption, split comma/newline tags, and reject oversized metadata]
# 引数: [image_path: inventoried image]
# 戻り値: [DatasetSampleInput: conservative captions or an empty automatic record]
# }
def _read_sidecar(image_path: Path) -> DatasetSampleInput:
    for suffix in (".txt", ".caption"):
        path = image_path.with_suffix(suffix)
        if not path.is_file() or path.is_symlink():
            continue
        if path.stat().st_size > MAX_SIDECAR_BYTES:
            raise ValueError(f"caption sidecar exceeds 64 KiB: {path.name}")
        text = path.read_text(encoding="utf-8-sig").strip()
        tags = tuple(
            dict.fromkeys(
                part.strip()
                for line in text.splitlines()
                for part in line.split(",")
                if part.strip()
            )
        )
        return DatasetSampleInput(image_path, raw_tags=tags, long_caption=text, source="sidecar")
    return DatasetSampleInput(image_path, source="none")


# {
# 責務: [_attributes_for: combine explicit labels and normalized tag taxonomy]
# 処理: [merge classifier/user labels and Character Registry identity/outfit evidence into stable axis rows]
# 引数: [sample: imported metadata, normalized_tags: canonical tag sequence]
# 戻り値: [tuple[tuple[str, tuple[str, ...]], ...]: sorted axes and labels]
# }
def _attributes_for(
    sample: DatasetSampleInput, normalized_tags: tuple[str, ...]
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    values: dict[str, set[str]] = {}
    for axis, labels in sample.attributes:
        values.setdefault(axis.strip().casefold(), set()).update(
            label.strip().casefold() for label in labels if label.strip()
        )
    for tag in normalized_tags:
        values.setdefault(category_for_tag(tag), set()).add(tag)
    if sample.registry:
        for axis, labels in (
            ("identity", sample.registry.identity + sample.registry.accepted_traits),
            ("clothing", sample.registry.outfit + sample.registry.variable_attributes),
        ):
            values.setdefault(axis, set()).update(tag.casefold() for tag in labels if tag.strip())
    return tuple((axis, tuple(sorted(labels))) for axis, labels in sorted(values.items()))


# {
# 責務: [_coverage_matrix: count configured task attributes in included samples]
# 処理: [apply user-required axes or task defaults and mark each absent required label]
# 引数: [config: task coverage settings, included: included image paths, attributes: per-image labels]
# 戻り値: [tuple[CoverageCell, ...]: complete required coverage matrix]
# }
def _coverage_matrix(
    config: CuratorConfig,
    included: dict[Path, tuple[str, str, int]],
    attributes: dict[Path, tuple[tuple[str, tuple[str, ...]], ...]],
) -> tuple[CoverageCell, ...]:
    requirements = dict(config.required_coverage) or _DEFAULT_COVERAGE[config.task.value]
    labels_by_group: dict[str, set[tuple[str, str]]] = {}
    for path, (group_id, _, _) in included.items():
        labels_by_group.setdefault(group_id, set()).update(
            (axis, label) for axis, labels in attributes[path] for label in set(labels)
        )
    counts = Counter(label for labels in labels_by_group.values() for label in labels)
    return tuple(
        CoverageCell(axis, label, counts[(axis, label)], True, counts[(axis, label)] == 0)
        for axis, required_labels in sorted(requirements.items())
        for label in required_labels
    )


# {
# 責務: [_regularization_inventory: validate and fingerprint prior images separately]
# 処理: [resolve safe local image paths and inspect them without mixing them into subject samples]
# 引数: [root: canonical dataset root, paths: regularization source paths]
# 戻り値: [tuple[tuple[Path, str], ...]: verified local path and SHA-256]
# }
def _regularization_inventory(
    root: Path, paths: Sequence[str | Path]
) -> tuple[tuple[Path, str], ...]:
    images = []
    for candidate in paths:
        path = _safe_child(root, Path(candidate))
        if path.suffix.casefold() not in IMAGE_EXTENSIONS:
            raise ValueError("regularization samples must be supported image files")
        images.append((path, inspect_image(path).sha256))
    return tuple(images)


# {
# 責務: [_curated_samples: assemble final per-image decisions]
# 処理: [join image, caption, duplicate, quality, override, split, weight, and provenance evidence]
# 引数: [inputs: source metadata, captions: caption plans, attributes: labels, features: measurements, groups: duplicate assignments, outliers: concerns, actions: user/automatic decisions, weights: trainer weights, splits: group split, config: task settings]
# 戻り値: [tuple[CuratedSample, ...]: sorted review rows]
# }
def _curated_samples(
    inputs: dict[Path, DatasetSampleInput],
    captions: dict[Path, CaptionSet],
    attributes: dict[Path, tuple[tuple[str, tuple[str, ...]], ...]],
    features: dict[Path, ImageFeatures],
    groups: dict[Path, tuple[str, str, int]],
    outliers: dict[Path, OutlierClass],
    actions: dict[Path, SampleAction],
    weights: dict[Path, float],
    splits: dict[Path, str],
    config: CuratorConfig,
) -> tuple[CuratedSample, ...]:
    return tuple(
        CuratedSample(
            image_path=path,
            image_id=features[path].sha256[:16],
            features=features[path],
            captions=captions[path],
            attributes=attributes[path],
            duplicate_group=groups[path][0],
            duplicate_kind=groups[path][1],
            outlier_class=outliers[path],
            action=actions[path],
            sample_weight=weights.get(path, 0.0),
            split=splits.get(path, "excluded"),
            crop_policy=config.crop_policy,
            source_kind=inputs[path].source_kind,
            provenance=inputs[path].provenance,
        )
        for path in sorted(inputs, key=lambda item: item.as_posix().casefold())
    )


# {
# 責務: [_duplicate_group_rows: serialize stable duplicate membership]
# 処理: [sort group identifiers and member paths for reproducible reporting]
# 引数: [groups: image-to-duplicate assignments]
# 戻り値: [tuple[tuple[str, tuple[Path, ...]], ...]: sorted duplicate groups]
# }
def _duplicate_group_rows(
    groups: dict[Path, tuple[str, str, int]],
) -> tuple[tuple[str, tuple[Path, ...]], ...]:
    return tuple(
        (
            group_id,
            tuple(
                sorted(
                    (path for path, (name, _, _) in groups.items() if name == group_id),
                    key=lambda path: path.as_posix().casefold(),
                )
            ),
        )
        for group_id in sorted({value[0] for value in groups.values()})
    )


# {
# 責務: [_fingerprint: hash all inputs and decisions needed to reproduce curation]
# 処理: [serialize versioned image/caption/group/action/split and regularization evidence canonically]
# 引数: [config: task controls, coverage_requirements: requested task labels, samples: complete review rows, regularization: prior image hashes]
# 戻り値: [str: lowercase SHA-256 curation fingerprint]
# }
def _fingerprint(
    config: CuratorConfig,
    coverage_requirements: dict[str, tuple[str, ...]],
    samples: tuple[CuratedSample, ...],
    regularization: tuple[tuple[Path, str], ...],
) -> str:
    payload = {
        "task": config.task.value,
        "base_family": config.base_family,
        "caption_policy": config.caption_policy.value,
        "crop_policy": config.crop_policy.value,
        "ratio": config.validation_ratio,
        "seed": config.seed,
        "threshold": config.duplicate_hamming_threshold,
        "maximum_weight": config.maximum_weight,
        "required_coverage": coverage_requirements,
        "algorithm_versions": {"image_analysis": 1, "caption_ownership": 1, "split": 1},
        "samples": [
            (
                sample.features.sha256,
                sample.features.perceptual_hash,
                sample.features.blur_score,
                sample.features.compression_score,
                sample.features.crop_quality,
                sample.features.face_visibility,
                sample.features.body_visibility,
                sample.features.concept_match,
                sample.captions.raw_tags,
                sample.captions.normalized_tags,
                sample.captions.short_caption,
                sample.captions.long_caption,
                sample.captions.concept_caption,
                sample.captions.trainer_caption,
                sample.captions.negative_tags,
                sample.captions.confidence,
                sample.captions.source,
                sample.captions.absorb_tags,
                sample.captions.variable_tags,
                sample.attributes,
                sample.duplicate_group,
                sample.duplicate_kind,
                sample.outlier_class.value,
                sample.action.value,
                sample.sample_weight,
                sample.split,
                sample.source_kind.value,
                sample.provenance,
            )
            for sample in samples
        ],
        "regularization": sorted(digest for _, digest in regularization),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# {
# 責務: [_quality_actions: classify measured concerns and select keep/weight/exclude defaults]
# 処理: [combine injected concept-match evidence, conservative quality proxies, label rarity and user action overrides]
# 引数: [inputs: sample metadata, attributes: normalized labels, features: measured image evidence, overrides: reviewed corrections]
# 戻り値: [tuple[dict[Path, OutlierClass], set[Path], dict[Path, SampleAction]]: outlier, low-weight and action maps]
# }
def _quality_actions(
    inputs: dict[Path, DatasetSampleInput],
    attributes: dict[Path, tuple[tuple[str, tuple[str, ...]], ...]],
    features: dict[Path, ImageFeatures],
    overrides: dict[Path, SampleOverride],
) -> tuple[dict[Path, OutlierClass], set[Path], dict[Path, SampleAction]]:
    label_frequency = Counter(
        (axis, label)
        for rows in attributes.values()
        for axis, labels in rows
        for label in set(labels)
    )
    outliers = {}
    low_weight = set()
    actions = {}
    for path, feature in features.items():
        override = overrides.get(path)
        if override and override.outlier_class:
            outlier = override.outlier_class
        elif feature.concept_match is False or inputs[path].concept_match is False:
            outlier = OutlierClass.CONCEPT_MISMATCH
        elif (
            feature.blur_score < 0.12
            or min(feature.width, feature.height) < 256
            or feature.compression_score > 0.9
        ):
            outlier = OutlierClass.LIKELY_BAD
        elif any(
            label_frequency[(axis, label)] == 1
            for axis, labels in attributes[path]
            for label in labels
        ):
            outlier = OutlierClass.UNUSUAL_USEFUL
        else:
            outlier = OutlierClass.NONE
        outliers[path] = outlier
        if outlier in {OutlierClass.CONCEPT_MISMATCH, OutlierClass.LIKELY_BAD}:
            low_weight.add(path)
        if override and override.action == SampleAction.LOW_WEIGHT:
            low_weight.add(path)
        elif override and override.action == SampleAction.KEEP:
            low_weight.discard(path)
        actions[path] = (
            override.action
            if override and override.action
            else SampleAction.LOW_WEIGHT
            if path in low_weight
            else SampleAction.KEEP
        )
    return outliers, low_weight, actions


# {
# 責務: [_split_and_weight: create duplicate-safe splits and capped sample weights]
# 処理: [exclude reviewed samples, apply consistent group-level split overrides, and calculate trainer weights]
# 引数: [groups: duplicate assignments, attributes: normalized labels, actions: sample actions, overrides: reviewed choices, config: split and weight controls, low_weight: auto quality review set]
# 戻り値: [tuple[dict[Path, tuple[str, str, int]], dict[Path, str], dict[Path, float]]: included groups, split map and weights]
# }
def _split_and_weight(
    groups: dict[Path, tuple[str, str, int]],
    attributes: dict[Path, tuple[tuple[str, tuple[str, ...]], ...]],
    actions: dict[Path, SampleAction],
    overrides: dict[Path, SampleOverride],
    config: CuratorConfig,
    low_weight: set[Path],
) -> tuple[dict[Path, tuple[str, str, int]], dict[Path, str], dict[Path, float]]:
    included = {path: groups[path] for path in groups if actions[path] != SampleAction.EXCLUDE}
    included_attributes = {path: attributes[path] for path in included}
    splits = split_by_duplicate_group(
        included, included_attributes, config.validation_ratio, config.seed
    )
    group_overrides: dict[str, str] = {}
    for path, override in overrides.items():
        if override.split is None or actions[path] == SampleAction.EXCLUDE:
            continue
        group_id = groups[path][0]
        previous = group_overrides.setdefault(group_id, override.split)
        if previous != override.split:
            raise ValueError("duplicate-group members cannot receive conflicting split overrides")
    for path, (group_id, _, _) in included.items():
        if group_id in group_overrides:
            splits[path] = group_overrides[group_id]
    if splits and "train" not in splits.values():
        raise ValueError("manual split overrides must leave at least one training group")
    manual_weights = {
        path: override.weight
        for path, override in overrides.items()
        if override.weight is not None and actions[path] != SampleAction.EXCLUDE
    }
    weights = sample_weights(
        included, included_attributes, config.maximum_weight, low_weight, manual_weights
    )
    return included, splits, weights


# {
# 責務: [DatasetCurationProcessor: inventory, analyze, and reproduce LoRA dataset decisions]
# フィールド: [no mutable state]
# 処理: [provide deterministic curation and caption-probe operations behind injectable local analyzers]
# }
class DatasetCurationProcessor:
    # {
    # 責務: [curate: build a reviewable task-aware dataset plan]
    # 処理: [inventory safely, normalize captions, group duplicates, score quality, split whole groups, and fingerprint all decisions]
    # 引数: [root: dataset directory, config: task rules, samples: optional explicit inventory, overrides: reviewed choices, regularization_images: separate prior images, evidence_provider: optional local vision classifier, similarity_provider: optional local duplicate model]
    # 戻り値: [DatasetAnalysis: samples, coverage, duplicate groups, warnings, and reproducibility fingerprint]
    # エラー: [ValueError: unsafe paths, duplicate inputs, invalid override, or excessive inventory]
    # }
    def curate(
        self,
        root: str | Path,
        config: CuratorConfig,
        samples: Sequence[DatasetSampleInput] | None = None,
        overrides: Sequence[SampleOverride] = (),
        regularization_images: Sequence[str | Path] = (),
        evidence_provider: ImageEvidenceProvider | None = None,
        similarity_provider: EmbeddingSimilarityProvider | None = None,
    ) -> DatasetAnalysis:
        dataset_root = Path(root).expanduser().resolve(strict=True)
        if not dataset_root.is_dir():
            raise ValueError("dataset root must be a local directory")
        if samples is None:
            paths = sorted(
                (
                    path
                    for path in dataset_root.rglob("*")
                    if path.suffix.casefold() in IMAGE_EXTENSIONS
                ),
                key=lambda path: path.as_posix().casefold(),
            )
            if len(paths) > MAX_DATASET_IMAGES:
                raise ValueError("dataset inventory exceeds the 20,000-image analysis limit")
            inputs = tuple(_read_sidecar(_safe_child(dataset_root, path)) for path in paths)
        else:
            inputs = tuple(samples)
        if not inputs or len(inputs) > MAX_DATASET_IMAGES:
            raise ValueError("dataset must contain 1..20,000 images")
        normalized_inputs: dict[Path, DatasetSampleInput] = {}
        for sample in inputs:
            path = _safe_child(dataset_root, sample.image_path)
            if path in normalized_inputs:
                raise ValueError(f"duplicate dataset input path: {path.name}")
            normalized_inputs[path] = sample
        override_map: dict[Path, SampleOverride] = {}
        for override in overrides:
            path = _safe_child(dataset_root, override.image_path)
            if path not in normalized_inputs or path in override_map:
                raise ValueError("each override must name one unique inventoried image")
            if override.weight is not None and (
                not math.isfinite(override.weight)
                or override.weight < 0.05
                or override.weight > config.maximum_weight
            ):
                raise ValueError("manual weight must be within the configured trainer weight range")
            override_map[path] = override

        captions = {
            path: build_captions(
                sample,
                config,
                override_map[path].absorb_tags if path in override_map else (),
                override_map[path].variable_tags if path in override_map else (),
            )
            for path, sample in normalized_inputs.items()
        }
        attributes = {
            path: _attributes_for(normalized_inputs[path], captions[path].normalized_tags)
            for path in normalized_inputs
        }
        features = {path: inspect_image(path, evidence_provider) for path in normalized_inputs}
        groups = group_duplicates(features, config.duplicate_hamming_threshold, similarity_provider)

        outliers, low_weight, decisions = _quality_actions(
            normalized_inputs, attributes, features, override_map
        )
        included_groups, splits, weights = _split_and_weight(
            groups, attributes, decisions, override_map, config, low_weight
        )

        requirements = dict(config.required_coverage) or _DEFAULT_COVERAGE[config.task.value]
        coverage = _coverage_matrix(config, included_groups, attributes)
        reg_images = _regularization_inventory(dataset_root, regularization_images)
        curated = _curated_samples(
            normalized_inputs,
            captions,
            attributes,
            features,
            groups,
            outliers,
            decisions,
            weights,
            splits,
            config,
        )
        duplicate_groups = _duplicate_group_rows(groups)
        warnings = []
        if not splits or not any(value == "validation" for value in splits.values()):
            warnings.append(
                "validation split unavailable because fewer than two independent duplicate groups remain"
            )
        if any(sample.source_kind == SourceKind.UNKNOWN for sample in curated):
            warnings.append("real/synthetic provenance is unknown for one or more images")
        if any(sample.captions.source == "none" for sample in curated):
            warnings.append(
                "one or more images have no caption/tag source; automatic semantic tagging was not run"
            )
        if any(sample.concept_match is None for sample in (features[path] for path in features)):
            warnings.append("vision concept match evidence is unavailable for one or more images")
        fingerprint = _fingerprint(config, requirements, curated, reg_images)
        return DatasetAnalysis(
            config.task,
            config.base_family,
            curated,
            coverage,
            tuple(cell for cell in coverage if cell.missing),
            duplicate_groups,
            fingerprint,
            tuple(warnings),
            tuple(reg_images),
        )

    # {
    # 責務: [compare_caption_policies: connect #55 probe search to multiple caption variants]
    # 処理: [submit bounded candidate captions and validate finite normalized probe scores]
    # 引数: [analysis: curated dataset, probe: injected local trainer comparison]
    # 戻り値: [tuple[tuple[str, float], ...]: scores sorted best-first]
    # }
    def compare_caption_policies(
        self, analysis: DatasetAnalysis, probe: CaptionPolicyProbe
    ) -> tuple[tuple[str, float], ...]:
        included = tuple(
            sample for sample in analysis.samples if sample.action != SampleAction.EXCLUDE
        )
        candidates = (
            ("full_tags", tuple(", ".join(sample.captions.normalized_tags) for sample in included)),
            (
                "variable_tags",
                tuple(", ".join(sample.captions.variable_tags) for sample in included),
            ),
            ("short", tuple(sample.captions.short_caption for sample in included)),
            ("long", tuple(sample.captions.long_caption for sample in included)),
            (
                "concept_variable",
                tuple(
                    ", ".join(
                        part
                        for part in (
                            sample.captions.concept_caption,
                            ", ".join(sample.captions.variable_tags),
                        )
                        if part
                    )
                    for sample in included
                ),
            ),
        )
        result = probe.compare(analysis, candidates)
        names = [name for name, _ in result]
        if (
            len(result) > 16
            or len(names) != len(set(names))
            or any(
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(score, (int, float))
                or not math.isfinite(score)
                or not 0 <= score <= 1
                for name, score in result
            )
        ):
            raise ValueError("caption probe must return at most 16 named normalized 0..1 scores")
        return tuple(sorted(result, key=lambda item: (-item[1], item[0])))
