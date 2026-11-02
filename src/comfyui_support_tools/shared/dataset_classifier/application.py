"""Dataset classification, evidence fusion, querying, and safe export planning."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from .contracts import (
    ClassificationEvidence,
    ClassificationResult,
)
from .transfer import DatasetExportService, _sidecars
from .validation import _valid_identifier

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
        self._export_service = DatasetExportService(self.sidecar_extensions)

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
    # 処理: [delegate validated review persistence to the export service]
    # 引数: [path: review destination, overrides: source path to axis labels]
    # 戻り値: [None: reviewed labels stored]
    # }
    @staticmethod
    def save_review_overrides(path, overrides):
        return DatasetExportService.save_review_overrides(path, overrides)

    # {
    # 責務: [load_review_overrides: load saved manual label corrections]
    # 処理: [delegate bounded JSON loading and validation to the export service]
    # 引数: [path: saved review file]
    # 戻り値: [dict: normalized source-to-axis corrections]
    # }
    @staticmethod
    def load_review_overrides(path):
        return DatasetExportService.load_review_overrides(path)

    # {
    # 責務: [apply_overrides: apply reviewed labels and retain manual evidence]
    # 処理: [delegate immutable result updates to the export service]
    # 引数: [results: classifications, overrides: source path to axis labels]
    # 戻り値: [tuple[ClassificationResult, ...]: reviewed results]
    # }
    @staticmethod
    def apply_overrides(results, overrides):
        return DatasetExportService.apply_overrides(results, overrides)

    # {
    # 責務: [curator_handoff: export classifications for dataset preparation]
    # 処理: [delegate transport-neutral payload creation to the export service]
    # 引数: [results: selected classifications]
    # 戻り値: [tuple[dict, ...]: curator handoff records]
    # }
    @staticmethod
    def curator_handoff(results):
        return DatasetExportService.curator_handoff(results)

    # {
    # 責務: [plan_export: create a dry-run destination plan]
    # 処理: [delegate query filtering and safe path construction to the export service]
    # 引数: [query: selection query, results: classifications, output_root: destination root, uncertain_label: fallback bucket]
    # 戻り値: [tuple[TransferRecord, ...]: reviewed transfer plan]
    # }
    @staticmethod
    def plan_export(query, results, output_root, uncertain_label="uncertain"):
        return DatasetExportService.plan_export(query, results, output_root, uncertain_label)

    # {
    # 責務: [execute_export: apply planned copy/move or write a manifest-only result]
    # 処理: [delegate collision-safe transfer and manifest handling to the export service]
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
        return self._export_service.execute_export(
            records, action, dry_run, collision_policy, sidecars, manifest_path
        )


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
