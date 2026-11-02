"""Dataset classification, evidence fusion, querying, and safe export planning."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from .contracts import (
    ClassificationEvidence,
    ClassificationResult,
    TransferRecord,
)
from .query import matches_query, validate_query

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"})
DEFAULT_SIDECARS = frozenset({".txt", ".caption", ".json", ".yaml", ".yml"})


# {
# 責務: [_Registration: associate classifier, axis, and fusion weight]
# フィールド: [axis, name, classifier, weight, priority]
# 処理: [retain adapter identity while fusing parallel evidence]
# }
@dataclass(frozen=True)
class _Registration:
    axis: str
    name: str
    classifier: object
    weight: float
    priority: int


# {
# 責務: [DatasetClassifierApplication: manage classifier adapters and safe dataset export]
# フィールド: [classifier registry, thresholds, sidecars, classification cache]
# 処理: [inventory, classify/fuse evidence, query, plan, and collision-safe copy/move]
# }
class DatasetClassifierApplication:
    # {
    # 責務: [__init__: configure confidence, disagreement and sidecar policies]
    # 処理: [initialize empty axis registry and in-memory cache]
    # 引数: [confidence_threshold: minimum label confidence, disagreement_threshold: review limit, sidecar_extensions: associated file suffixes]
    # 戻り値: [None: initialized dataset application]
    # }
    def __init__(
        self,
        confidence_threshold=0.55,
        disagreement_threshold=0.45,
        sidecar_extensions=DEFAULT_SIDECARS,
    ):
        if not 0 <= confidence_threshold <= 1 or not 0 <= disagreement_threshold <= 1:
            raise ValueError("classification thresholds must be within 0..1")
        if any(not isinstance(ext, str) for ext in sidecar_extensions):
            raise ValueError("sidecar extensions must be strings")
        normalized = frozenset(
            ext.casefold() if ext.startswith(".") else f".{ext.casefold()}"
            for ext in sidecar_extensions
        )
        if any(not ext[1:].isalnum() for ext in normalized):
            raise ValueError("sidecar extensions must be plain file suffixes")
        self.confidence_threshold = confidence_threshold
        self.disagreement_threshold = disagreement_threshold
        self.sidecar_extensions = normalized
        self._registrations: dict[str, list[_Registration]] = defaultdict(list)
        self._cache: dict[str, ClassificationResult] = {}

    # {
    # 責務: [register: attach an evidence provider to a classification axis]
    # 処理: [validate axis/name/weight and retain stable registry order]
    # 引数: [axis: category axis, classifier: adapter, name: source identifier, weight: fusion multiplier, priority: metadata precedence]
    # 戻り値: [None: adapter registered]
    # }
    def register(self, axis, classifier, name=None, weight=1.0, priority=0):
        if not _valid_identifier(axis) or not callable(getattr(classifier, "classify", None)):
            raise ValueError("registration needs a safe axis and classify(image_path) adapter")
        if not name:
            name = type(classifier).__name__
        if (
            not _valid_identifier(name)
            or not isinstance(weight, (int, float))
            or not 0 < weight <= 100
        ):
            raise ValueError("classifier name or weight is invalid")
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError("classifier priority must be an integer")
        self._registrations[axis].append(
            _Registration(axis, name, classifier, float(weight), priority)
        )
        self._cache.clear()

    # {
    # 責務: [inventory: recursively list eligible image files under an input root]
    # 処理: [exclude hidden and symlink files unless explicitly enabled; keep stable ordering]
    # 引数: [root: input folder, recursive: traverse subfolders, include_hidden: include dotfiles, follow_symlinks: follow file symlinks]
    # 戻り値: [tuple[Path, ...]: sorted eligible image paths]
    # }
    @staticmethod
    def inventory(root, recursive=True, include_hidden=False, follow_symlinks=False):
        base = Path(root).resolve(strict=True)
        if not base.is_dir():
            raise ValueError("input root must be a directory")
        candidates = base.rglob("*") if recursive else base.iterdir()
        images = []
        for path in candidates:
            if not path.is_file() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
                continue
            relative = path.relative_to(base)
            if not include_hidden and any(part.startswith(".") for part in relative.parts):
                continue
            if path.is_symlink() and not follow_symlinks:
                continue
            images.append(path)
        return tuple(sorted(images, key=lambda item: item.relative_to(base).as_posix().casefold()))

    # {
    # 責務: [classify: classify one image and fuse multi-source evidence per axis]
    # 処理: [reuse stat-keyed cache; metadata priority overrides model evidence; flag low confidence/disagreement]
    # 引数: [image_path: source image, axes: optional selected classifier axes]
    # 戻り値: [ClassificationResult: normalized labels, confidence, evidence and uncertainty]
    # }
    def classify(self, image_path, axes=None):
        original = Path(image_path)
        if original.is_symlink():
            raise ValueError("classification source cannot be a symbolic link")
        path = original.resolve(strict=True)
        if not path.is_file() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
            raise ValueError("classification source must be a supported image file")
        selected = tuple(axes) if axes is not None else tuple(self._registrations)
        unknown = set(selected) - self._registrations.keys()
        if unknown:
            raise ValueError(f"no classifier registered for axes: {', '.join(sorted(unknown))}")
        stat = path.stat()
        signature = (
            f"{self._registry_signature(selected)}|"
            f"{_sidecar_signature(path, self.sidecar_extensions)}"
        )
        cache_key = _fingerprint(path, stat.st_size, stat.st_mtime_ns, signature)
        if cache_key in self._cache:
            return self._cache[cache_key]
        evidence = []
        for axis in selected:
            for registration in self._registrations[axis]:
                output = registration.classifier.classify(path)
                if not isinstance(output, (tuple, list)):
                    raise ValueError(
                        f"classifier {registration.name} must return evidence sequence"
                    )
                for item in output:
                    if not isinstance(item, ClassificationEvidence) or item.axis != axis:
                        raise ValueError(
                            f"classifier {registration.name} returned evidence for the wrong axis"
                        )
                    if (
                        not isinstance(item.label, str)
                        or not item.label.strip()
                        or not isinstance(item.source, str)
                        or not isinstance(item.confidence, (int, float))
                        or isinstance(item.confidence, bool)
                        or not math.isfinite(item.confidence)
                        or not 0 <= item.confidence <= 1
                        or not isinstance(item.weight, (int, float))
                        or isinstance(item.weight, bool)
                        or not math.isfinite(item.weight)
                        or not 0 < item.weight <= 100
                    ):
                        raise ValueError(
                            f"classifier {registration.name} returned invalid evidence"
                        )
                    evidence.append(
                        replace(
                            item,
                            source=item.source or registration.name,
                            weight=item.weight * registration.weight,
                            priority=max(item.priority, registration.priority),
                        )
                    )
        result = self._fuse(path, tuple(evidence), selected)
        after = path.stat()
        if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
            raise RuntimeError("dataset image changed while it was being classified")
        self._cache[cache_key] = result
        return result

    # {
    # 責務: [_registry_signature: bind persistent cache keys to adapter identities]
    # 処理: [include classifier name/type/version/weight/priority for requested axes]
    # 引数: [axes: selected classification axes]
    # 戻り値: [str: stable adapter configuration signature]
    # }
    def _registry_signature(self, axes):
        entries = []
        for axis in axes:
            for item in self._registrations[axis]:
                classifier_type = type(item.classifier)
                version = getattr(item.classifier, "version", "")
                entries.append(
                    f"{axis}:{item.name}:{classifier_type.__module__}.{classifier_type.__qualname__}:"
                    f"{version}:{item.weight}:{item.priority}"
                )
        return "|".join(entries)

    # {
    # 責務: [_fuse: merge label evidence using priority and weighted confidence]
    # 処理: [keep alternate labels, compute disagreement, and mark uncertain axes]
    # 引数: [path: source image, evidence: ordered claims, axes: requested axis names]
    # 戻り値: [ClassificationResult: fused normalized classification]
    # }
    def _fuse(self, path, evidence, axes):
        labels_by_axis, confidences, alternates, disagreements, uncertain = [], [], [], [], []
        for axis in axes:
            claims = [item for item in evidence if item.axis == axis]
            if not claims:
                labels_by_axis.append((axis, ("uncertain",)))
                confidences.append((axis, 0.0))
                alternates.append((axis, ()))
                disagreements.append((axis, 0.0))
                uncertain.append(axis)
                continue
            priority = max(item.priority for item in claims)
            if priority > 0:
                claims = [item for item in claims if item.priority == priority]
            scores = defaultdict(lambda: [0.0, 0.0])
            for claim in claims:
                scores[claim.label][0] += claim.confidence * claim.weight
                scores[claim.label][1] += claim.weight
            ranked = sorted(
                ((label, weighted / weight) for label, (weighted, weight) in scores.items()),
                key=lambda pair: (-pair[1], pair[0].casefold()),
            )
            top_label, top_score = ranked[0]
            disagreement = (
                0.0
                if len(ranked) == 1
                else max(0.0, 1.0 - top_score / sum(score for _, score in ranked))
            )
            chosen = tuple(label for label, score in ranked if score >= self.confidence_threshold)
            is_uncertain = (
                top_score < self.confidence_threshold or disagreement > self.disagreement_threshold
            )
            labels_by_axis.append(
                (axis, ("uncertain",) if is_uncertain else chosen or (top_label,))
            )
            confidences.append((axis, top_score))
            alternates.append((axis, tuple(label for label, _score in ranked[1:])))
            disagreements.append((axis, disagreement))
            if is_uncertain:
                uncertain.append(axis)
        return ClassificationResult(
            path,
            tuple(labels_by_axis),
            tuple(confidences),
            evidence,
            tuple(alternates),
            tuple(disagreements),
            tuple(uncertain),
        )

    # {
    # 責務: [classify_folder: classify recursive inventory with selected axes and optional disk cache]
    # 処理: [reuse valid stat-fingerprint entries and atomically refresh cache after each run]
    # 引数: [root: dataset root, axes: selected classifiers, recursive/include_hidden/follow_symlinks: inventory options, cache_path: optional index JSON]
    # 戻り値: [tuple[ClassificationResult, ...]: ordered per-image results]
    # }
    def classify_folder(
        self,
        root,
        axes=None,
        recursive=True,
        include_hidden=False,
        follow_symlinks=False,
        cache_path=None,
        review_path=None,
    ):
        base = Path(root).resolve(strict=True)
        paths = self.inventory(base, recursive, include_hidden, follow_symlinks)
        disk_cache = _load_cache(Path(cache_path)) if cache_path is not None else {}
        selected = tuple(axes) if axes is not None else tuple(self._registrations)
        results = []
        for path in paths:
            stat = path.stat()
            key = _fingerprint(
                path,
                stat.st_size,
                stat.st_mtime_ns,
                f"{self._registry_signature(selected)}|"
                f"{_sidecar_signature(path, self.sidecar_extensions)}",
            )
            result = disk_cache.get(key)
            if result is None:
                result = self.classify(path, selected)
                disk_cache[key] = result
            results.append(result)
        if cache_path is not None:
            _save_cache(Path(cache_path), disk_cache)
        if review_path is not None:
            return self.apply_overrides(tuple(results), self.load_review_overrides(review_path))
        return tuple(results)

    # {
    # 責務: [save_review_overrides: persist reviewed labels for future classifications]
    # 処理: [validate source/axis/label mappings and atomically replace the review JSON]
    # 引数: [path: review file destination, overrides: source path to axis labels]
    # 戻り値: [None: reviewed labels stored]
    # }
    @staticmethod
    def save_review_overrides(path, overrides):
        normalized = {}
        for source, axes in overrides.items():
            if not isinstance(source, str) or not isinstance(axes, dict):
                raise ValueError("review overrides need source paths and axis mappings")
            normalized[str(Path(source).resolve())] = {}
            for axis, values in axes.items():
                if isinstance(values, str):
                    values = (values,)
                if (
                    not _valid_identifier(axis)
                    or not isinstance(values, (tuple, list))
                    or not values
                    or any(not _safe_label(value) for value in values)
                ):
                    raise ValueError("review override labels are invalid")
                normalized[str(Path(source).resolve())][axis] = list(dict.fromkeys(values))
        target = Path(path)
        if target.is_symlink():
            raise ValueError("review override file cannot be a symlink")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = (json.dumps(normalized, ensure_ascii=False, indent=2) + "\n").encode()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=f".{target.name}.", delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    # {
    # 責務: [load_review_overrides: load bounded, validated manual label corrections]
    # 処理: [parse source/axis mappings and reject malformed or unsafe labels]
    # 引数: [path: saved manual review JSON]
    # 戻り値: [dict[str, dict[str, tuple[str, ...]]]: corrections ready for classification]
    # }
    @staticmethod
    def load_review_overrides(path):
        target = Path(path)
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("review override file must be a bounded regular file")
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ValueError("review override file is not valid JSON") from None
        if not isinstance(data, dict):
            raise ValueError("review override file must contain an object")
        normalized = {}
        for source, axes in data.items():
            if not isinstance(source, str) or not isinstance(axes, dict):
                raise ValueError("review override entries are invalid")
            normalized[source] = {}
            for axis, values in axes.items():
                if (
                    not _valid_identifier(axis)
                    or not isinstance(values, list)
                    or not values
                    or any(not _safe_label(value) for value in values)
                ):
                    raise ValueError("review override labels are invalid")
                normalized[source][axis] = tuple(dict.fromkeys(values))
        return normalized

    # {
    # 責務: [apply_overrides: apply reviewed labels and retain manual evidence]
    # 処理: [replace selected axis labels, set human confidence, and preserve other findings]
    # 引数: [results: existing classifications, overrides: source path to axis labels]
    # 戻り値: [tuple[ClassificationResult, ...]: manually reviewed results]
    # }
    @staticmethod
    def apply_overrides(results, overrides):
        updated = []
        for result in results:
            selected = overrides.get(str(result.source), {})
            if not isinstance(selected, dict):
                raise ValueError("manual overrides must map axes to label sequences")
            labels = dict(result.labels)
            confidence = dict(result.confidence)
            evidence = list(result.evidence)
            normalized_overrides = {}
            for axis, values in selected.items():
                if isinstance(values, str):
                    values = (values,)
                if (
                    not _valid_identifier(axis)
                    or not isinstance(values, (tuple, list))
                    or not values
                    or any(not _safe_label(value) for value in values)
                ):
                    raise ValueError("manual label override is invalid")
                normalized = tuple(dict.fromkeys(values))
                normalized_overrides[axis] = normalized
                labels[axis] = normalized
                confidence[axis] = 1.0
                evidence.extend(
                    ClassificationEvidence(axis, value, 1.0, "manual_review", 1.0, 1000)
                    for value in normalized
                )
            updated.append(
                replace(
                    result,
                    labels=tuple(sorted(labels.items())),
                    confidence=tuple(sorted(confidence.items())),
                    evidence=tuple(evidence),
                    uncertain_axes=tuple(
                        axis for axis in result.uncertain_axes if axis not in normalized_overrides
                    ),
                    manual_overrides=tuple(sorted(normalized_overrides.items())),
                )
            )
        return tuple(updated)

    # {
    # 責務: [curator_handoff: export normalized classifications for dataset preparation]
    # 処理: [preserve labels, cluster IDs, confidence, evidence and source paths]
    # 引数: [results: selected per-image classification results]
    # 戻り値: [tuple[dict, ...]: transport-neutral #356-style handoff records]
    # }
    @staticmethod
    def curator_handoff(results):
        payload = []
        for result in results:
            labels = {axis: tuple(values) for axis, values in result.labels}
            payload.append(
                {
                    "source_path": str(result.source),
                    "labels": labels,
                    "cluster_ids": tuple(
                        value
                        for values in labels.values()
                        for value in values
                        if value.startswith("style_cluster_")
                    ),
                    "confidence": dict(result.confidence),
                    "style_descriptors": labels.get("style", ()),
                    "background_class": labels.get("background", ()),
                    "character_ids": labels.get("character", ()),
                    "provenance": tuple(
                        {
                            "axis": evidence.axis,
                            "label": evidence.label,
                            "source": evidence.source,
                            "confidence": evidence.confidence,
                        }
                        for evidence in result.evidence
                    ),
                }
            )
        return tuple(payload)

    # {
    # 責務: [plan_export: filter results and create dry-run destination records]
    # 処理: [apply query expression, axis order, uncertainty buckets, and relative path policy]
    # 引数: [query: selection query, results: classifications, output_root: planned export root, uncertain_label: fallback bucket]
    # 戻り値: [tuple[TransferRecord, ...]: stable transfer plan suitable for review]
    # }
    @staticmethod
    def plan_export(query, results, output_root, uncertain_label="uncertain"):
        validate_query(query)
        root = Path(query.root).resolve(strict=True)
        destination_root = Path(output_root).resolve()
        if destination_root == root or root in destination_root.parents:
            raise ValueError("output root must be outside the input dataset")
        selected_axes = (
            query.axes or tuple(axis for axis, _labels in results[0].labels)
            if results
            else query.axes
        )
        if any(not _valid_identifier(axis) for axis in selected_axes) or not _safe_label(
            uncertain_label
        ):
            raise ValueError("export axes or uncertain label are invalid")
        records = []
        for result in results:
            if not matches_query(query, result):
                continue
            labels = dict(result.labels)
            parts = []
            for axis in selected_axes:
                values = labels.get(axis, (uncertain_label,))
                bucket = "+".join(_slug(value) for value in values) or uncertain_label
                parts.append(f"{axis}={bucket}")
            destination = destination_root.joinpath(*parts)
            if query.preserve_relative:
                try:
                    relative = result.source.resolve(strict=True).relative_to(root)
                except ValueError:
                    raise ValueError("classification source is outside query root") from None
                destination /= relative.parent
            destination /= result.source.name
            records.append(
                TransferRecord(
                    result.source,
                    destination,
                    query.action,
                    result.labels,
                    result.confidence,
                    result.evidence,
                    result.manual_overrides,
                )
            )
        return tuple(records)

    # {
    # 責務: [execute_export: apply planned copy/move or write a manifest-only result]
    # 処理: [dry-run by default; copy and verify image/sidecars before deleting move sources]
    # 引数: [records: reviewed plan, action: copy/move/manifest, dry_run: no writes by default, collision_policy: suffix or skip, sidecars: transfer associated files, manifest_path: optional manifest destination]
    # 戻り値: [tuple[TransferRecord, ...]: records with resolved destination paths]
    # }
    def execute_export(
        self,
        records,
        action="manifest",
        dry_run=True,
        collision_policy="suffix",
        sidecars=True,
        manifest_path=None,
    ):
        if action not in {"copy", "move", "manifest"} or collision_policy not in {"suffix", "skip"}:
            raise ValueError("unsupported export action or collision policy")
        resolved = []
        planned = []
        reserved = set()
        for record in records:
            files = [record.source]
            if sidecars:
                files.extend(_sidecars(record.source, self.sidecar_extensions))
            destination = record.destination
            if destination is not None:
                conflict = (
                    destination.exists()
                    or any(destination.with_suffix(ext).exists() for ext in self.sidecar_extensions)
                    or destination in reserved
                )
                if collision_policy == "suffix":
                    destination = _collision_safe_destination(
                        destination, self.sidecar_extensions, reserved
                    )
                if collision_policy == "skip" and conflict:
                    continue
                reserved.add(destination)
            updated = replace(record, destination=destination, action=action)
            planned.append((updated, files))
            resolved.append(updated)
        if dry_run:
            return tuple(resolved)
        created = []
        try:
            for record, files in planned:
                if action == "manifest":
                    continue
                if record.destination is None:
                    raise ValueError("copy and move records require a destination")
                output_files = [record.destination]
                output_files.extend(
                    record.destination.with_suffix(path.suffix) for path in files[1:]
                )
                for source, target in zip(files, output_files, strict=True):
                    _copy_verified(source, target)
                    created.append(target)
        except BaseException:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        if action == "move":
            for _record, files in planned:
                for source in files:
                    source.unlink()
        if manifest_path is not None:
            _write_manifest(Path(manifest_path), tuple(resolved))
        return tuple(resolved)


# {
# 責務: [SidecarMetadataClassifier: convert adjacent JSON metadata labels into high-priority evidence]
# フィールド: [axes, maximum sidecar size]
# 処理: [reuse existing downloader metadata without invoking image models]
# }
class SidecarMetadataClassifier:
    # {
    # 責務: [__init__: set allowed metadata axes]
    # 処理: [normalize a non-empty axis set]
    # 引数: [axes: label axes recognized in a JSON sidecar]
    # 戻り値: [None: initialized metadata adapter]
    # }
    def __init__(self, axes):
        self.axes = frozenset(axes)
        if not self.axes or any(not _valid_identifier(axis) for axis in self.axes):
            raise ValueError("metadata classifier requires valid axis names")

    # {
    # 責務: [classify: read bounded adjacent JSON metadata into label evidence]
    # 処理: [accept axis -> string/list labels or scored label mappings]
    # 引数: [image_path: source image]
    # 戻り値: [tuple[ClassificationEvidence, ...]: metadata-priority claims]
    # }
    def classify(self, image_path):
        path = Path(image_path)
        sidecar = path.with_suffix(".json")
        if sidecar.is_symlink() or not sidecar.is_file() or sidecar.stat().st_size > 1024 * 1024:
            return ()
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ()
        if not isinstance(payload, dict):
            return ()
        source_metadata = payload.get("labels", payload)
        if not isinstance(source_metadata, dict):
            return ()
        evidence = []
        for axis in self.axes:
            values = source_metadata.get(axis, ())
            if isinstance(values, str):
                values = (values,)
            if isinstance(values, (tuple, list)):
                for value in values:
                    if isinstance(value, str) and value.strip():
                        evidence.append(
                            ClassificationEvidence(
                                axis, value.strip(), 1.0, "sidecar_metadata", 1.0, 100
                            )
                        )
                    elif isinstance(value, dict) and isinstance(value.get("label"), str):
                        confidence = value.get("confidence", 1.0)
                        if (
                            isinstance(confidence, (int, float))
                            and not isinstance(confidence, bool)
                            and math.isfinite(confidence)
                            and 0 <= confidence <= 1
                        ):
                            evidence.append(
                                ClassificationEvidence(
                                    axis,
                                    value["label"],
                                    confidence,
                                    "sidecar_metadata",
                                    1.0,
                                    100,
                                )
                            )
        return tuple(evidence)


# {
# 責務: [_copy_verified: copy one source into an exclusively reserved output]
# 処理: [copy to a sibling temporary, verify size/hash, then atomically replace reservation]
# 引数: [source: input file, destination: no-overwrite output path]
# 戻り値: [None: verified file installed]
# }
def _copy_verified(source, destination):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_file():
        raise ValueError("transfer source must be a regular non-symlink file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
        shutil.copy2(source, temporary)
        if source.stat().st_size != temporary.stat().st_size or _sha256(source) != _sha256(
            temporary
        ):
            raise OSError("copied file failed size/hash verification")
        os.replace(temporary, destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


# {
# 責務: [_sidecars: find supported same-stem caption and metadata files]
# 処理: [sort sidecars deterministically and exclude symlinks]
# 引数: [image: source image, extensions: configured suffix set]
# 戻り値: [list[Path]: adjacent regular sidecars]
# }
def _sidecars(image, extensions):
    return sorted(
        (
            path
            for path in image.parent.glob(f"{image.stem}.*")
            if path != image
            and path.suffix.casefold() in extensions
            and path.is_file()
            and not path.is_symlink()
        ),
        key=lambda path: path.suffix.casefold(),
    )


# {
# 責務: [_collision_safe_destination: choose deterministic suffix without overwriting image/sidecars]
# 処理: [probe base name then increment numbered stems while any paired artifact exists]
# 引数: [destination: desired image output, extensions: sidecar suffixes]
# 戻り値: [Path: free output image path]
# }
def _collision_safe_destination(destination, extensions, reserved=()):
    destination = Path(destination)
    candidate = destination
    index = 1
    while (
        candidate.exists()
        or any(candidate.with_suffix(ext).exists() for ext in extensions)
        or candidate in reserved
    ):
        candidate = destination.with_name(f"{destination.stem}_{index}{destination.suffix}")
        index += 1
    return candidate


# {
# 責務: [_write_manifest: reserve and atomically write normalized transfer records]
# 処理: [serialize evidence and refuse replacement of an existing manifest]
# 引数: [path: manifest destination, records: completed or planned transfers]
# 戻り値: [None: manifest installed]
# }
def _write_manifest(path, records):
    payload = {
        "schema_version": 1,
        "records": [
            {
                "source_path": str(item.source),
                "destination_path": str(item.destination) if item.destination else None,
                "action": item.action,
                "classification": {axis: list(values) for axis, values in item.labels},
                "confidence": dict(item.confidence),
                "evidence": [
                    {
                        "axis": e.axis,
                        "label": e.label,
                        "confidence": e.confidence,
                        "source": e.source,
                        "weight": e.weight,
                        "priority": e.priority,
                    }
                    for e in item.evidence
                ],
                "manual_overrides": {axis: list(values) for axis, values in item.manual_overrides},
            }
            for item in records
        ],
    }
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    _copy = Path(path)
    _copy.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(_copy, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        _copy.unlink(missing_ok=True)
        raise


# {
# 責務: [_load_cache: load bounded cached classification rows]
# 処理: [ignore malformed cache entries and reconstruct typed result/evidence objects]
# 引数: [path: optional cache JSON]
# 戻り値: [dict[str, ClassificationResult]: usable cache records]
# }
def _load_cache(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        results = {}
        for key, item in data.items():
            evidence = tuple(ClassificationEvidence(**entry) for entry in item["evidence"])
            results[key] = ClassificationResult(
                Path(item["source"]),
                tuple((axis, tuple(labels)) for axis, labels in item["labels"].items()),
                tuple(item["confidence"].items()),
                evidence,
                tuple((axis, tuple(labels)) for axis, labels in item.get("alternates", {}).items()),
                tuple(item.get("disagreement", {}).items()),
                tuple(item.get("uncertain_axes", ())),
                tuple(
                    (axis, tuple(labels))
                    for axis, labels in item.get("manual_overrides", {}).items()
                ),
            )
        return results
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {}


# {
# 責務: [_save_cache: atomically persist classification cache entries]
# 処理: [serialize stable keys and replace cache file through a sibling temporary]
# 引数: [path: cache destination, values: keyed typed results]
# 戻り値: [None: cache file atomically updated]
# }
def _save_cache(path, values):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("classification cache cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = {}
    for key, result in values.items():
        rows[key] = {
            "source": str(result.source),
            "labels": {axis: list(labels) for axis, labels in result.labels},
            "confidence": dict(result.confidence),
            "evidence": [e.__dict__ for e in result.evidence],
            "alternates": {axis: list(labels) for axis, labels in result.alternates},
            "disagreement": dict(result.disagreement),
            "uncertain_axes": list(result.uncertain_axes),
            "manual_overrides": {axis: list(labels) for axis, labels in result.manual_overrides},
        }
    payload = (json.dumps(rows, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


# {
# 責務: [_fingerprint: key one file and classifier configuration by content-changing metadata]
# 処理: [use canonical path, size, mtime and adapter signature for incremental cache reuse]
# 引数: [path: image path, size: byte length, mtime_ns: modification time, signature: classifier configuration]
# 戻り値: [str: stable cache key]
# }
def _fingerprint(path, size, mtime_ns, signature):
    return hashlib.sha256(
        f"{Path(path).resolve()}\0{size}\0{mtime_ns}\0{signature}".encode()
    ).hexdigest()


# {
# 責務: [_sidecar_signature: invalidate classification cache when metadata files change]
# 処理: [include path, size and modification time for every configured adjacent sidecar]
# 引数: [image: source image, extensions: supported sidecar suffixes]
# 戻り値: [str: deterministic metadata fingerprint]
# }
def _sidecar_signature(image, extensions):
    metadata = []
    for path in _sidecars(Path(image), extensions):
        stat = path.stat()
        metadata.append(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}")
    return hashlib.sha256("\0".join(metadata).encode()).hexdigest()


# {
# 責務: [_sha256: hash file bytes for transfer verification]
# 処理: [stream bounded chunks without loading whole images into memory]
# 引数: [path: file path]
# 戻り値: [str: lowercase SHA-256 digest]
# }
def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# {
# 責務: [_slug: sanitize category labels before using them as folder names]
# 処理: [replace path separators/control chars and bound name length]
# 引数: [label: predicted or reviewed label]
# 戻り値: [str: safe plain directory component]
# }
def _slug(label):
    if not _safe_label(label):
        raise ValueError("classification label is not safe")
    result = "".join(
        "_" if char in '/\\<>:"|?*' or ord(char) < 32 else char for char in label.strip()
    )
    result = result.strip(" .")[:80]
    if not result or result in {".", ".."}:
        raise ValueError("classification label is not safe")
    return result


# {
# 責務: [_safe_label: bound and validate a label before manifest or path use]
# 処理: [reject empty strings and control characters]
# 引数: [label: candidate classification label]
# 戻り値: [bool: label is acceptable]
# }
def _safe_label(label):
    return (
        isinstance(label, str)
        and 1 <= len(label.strip()) <= 256
        and not any(ord(char) < 32 for char in label)
    )


# {
# 責務: [_valid_identifier: validate axis and adapter identifiers]
# 処理: [allow short portable alphanumeric underscore/hyphen values]
# 引数: [value: candidate identifier]
# 戻り値: [bool: identifier is safe]
# }
def _valid_identifier(value):
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 64
        and value[0].isalnum()
        and all(char.isalnum() or char in "_-" for char in value)
    )
