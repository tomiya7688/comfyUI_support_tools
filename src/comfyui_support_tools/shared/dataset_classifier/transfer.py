"""Safe dataset export planning, review persistence, and file transfer."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from .contracts import ClassificationEvidence, TransferRecord
from .query import matches_query, validate_query
from .validation import _safe_label, _valid_identifier


# {
# 責務: [DatasetExportService: persist manual review and execute safe dataset transfers]
# フィールド: [sidecar suffix policy]
# 処理: [query, plan, copy/move, collision control, and auditable manifests]
# }
class DatasetExportService:
    # {
    # 責務: [__init__: configure associated sidecars for export]
    # 処理: [retain normalized suffixes from the owning application]
    # 引数: [sidecar_extensions: allowed metadata suffixes]
    # 戻り値: [None: initialized export service]
    # }
    def __init__(self, sidecar_extensions):
        self.sidecar_extensions = sidecar_extensions

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
                possible_outputs = {destination} | {
                    destination.with_suffix(ext) for ext in self.sidecar_extensions
                }
                conflict = any(path.exists() or path in reserved for path in possible_outputs)
                if collision_policy == "suffix":
                    destination = _collision_safe_destination(
                        destination, self.sidecar_extensions, reserved
                    )
                if collision_policy == "skip" and conflict:
                    continue
                reserved.add(destination)
                reserved.update(destination.with_suffix(ext) for ext in self.sidecar_extensions)
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
            if manifest_path is not None:
                _write_manifest(Path(manifest_path), tuple(resolved))
        except BaseException:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        if action == "move":
            for _record, files in planned:
                for source in files:
                    source.unlink()
        return tuple(resolved)


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
        or any(candidate.with_suffix(ext) in reserved for ext in extensions)
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
