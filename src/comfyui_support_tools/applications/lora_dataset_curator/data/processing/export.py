"""Transactional export of curated datasets and trainer configuration templates."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path

from comfyui_support_tools.shared.contracts.dataset_curator import (
    CuratedSample,
    DatasetAnalysis,
    SampleAction,
)

SUPPORTED_TRAINERS = frozenset({"sd-scripts", "simpletuner", "ai-toolkit"})


# {
# 責務: [_write_json: write stable UTF-8 JSON metadata]
# 処理: [serialize sorted, indented JSON with a trailing newline]
# 引数: [path: staged output path, value: JSON-compatible value]
# 戻り値: [None: file written]
# }
def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


# {
# 責務: [_copy_verified: copy an unchanged regular image without following links]
# 処理: [open with O_NOFOLLOW, stream/hash into staging, and compare source identity plus the expected curation digest]
# 引数: [source: curated source image, target: staging output file, expected_sha256: inspection fingerprint]
# 戻り値: [None: exact source bytes copied]
# エラー: [ValueError: source is a link/non-regular/changed file]
# }
def _copy_verified(source: Path, target: Path, expected_sha256: str) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(source, flags)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("dataset export accepts only regular source files")
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as reader, target.open("xb") as writer:
            for block in iter(lambda: reader.read(1024 * 1024), b""):
                digest.update(block)
                writer.write(block)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise ValueError("dataset source changed during export")
        if digest.hexdigest() != expected_sha256:
            raise ValueError("dataset source fingerprint changed after curation")
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
    finally:
        os.close(descriptor)


# {
# 責務: [_copy_sample: copy a reviewed image/caption pair and create its manifest row]
# 処理: [choose a stable filename, verify source bytes against the analysis hash, and serialize all review evidence]
# 引数: [stage: isolated output directory, sample: curated image, occurrence: exact-content duplicate suffix]
# 戻り値: [dict[str, object]: manifest record for the copied image]
# エラー: [ValueError: source changed after analysis]
# }
def _copy_sample(stage: Path, sample: CuratedSample, occurrence: int) -> dict[str, object]:
    split = sample.split if sample.split in {"train", "validation"} else "train"
    suffix = sample.image_path.suffix.casefold()
    image_name = f"{sample.features.sha256}{suffix}"
    if occurrence:
        image_name = f"{sample.features.sha256}-{occurrence}{suffix}"
    image_target = stage / split / image_name
    _copy_verified(sample.image_path, image_target, sample.features.sha256)
    caption_path = image_target.with_suffix(".txt")
    caption_path.write_text(sample.captions.trainer_caption.strip() + "\n", encoding="utf-8")
    return {
        "image_id": sample.image_id,
        "image": f"{split}/{image_name}",
        "caption": f"{split}/{caption_path.name}",
        "captions": {
            "raw_tags": list(sample.captions.raw_tags),
            "normalized_tags": list(sample.captions.normalized_tags),
            "short": sample.captions.short_caption,
            "long": sample.captions.long_caption,
            "concept": sample.captions.concept_caption,
            "selected": sample.captions.trainer_caption,
            "negative_tags": list(sample.captions.negative_tags),
            "confidence": sample.captions.confidence,
            "source": sample.captions.source,
            "concept_owned": list(sample.captions.absorb_tags),
            "variable": list(sample.captions.variable_tags),
        },
        "attributes": {axis: list(labels) for axis, labels in sample.attributes},
        "sha256": sample.features.sha256,
        "perceptual_hash": sample.features.perceptual_hash,
        "dimensions": [sample.features.width, sample.features.height],
        "quality_proxies": {
            "blur_sharpness": sample.features.blur_score,
            "compression_blocking": sample.features.compression_score,
            "aspect_preservation": sample.features.crop_quality,
            "face_visibility": sample.features.face_visibility,
            "body_visibility": sample.features.body_visibility,
            "concept_match": sample.features.concept_match,
        },
        "duplicate_group": sample.duplicate_group,
        "duplicate_kind": sample.duplicate_kind,
        "outlier": sample.outlier_class.value,
        "action": sample.action.value,
        "sample_weight": sample.sample_weight,
        "split": split,
        "crop_policy": sample.crop_policy.value,
        "source_kind": sample.source_kind.value,
        "provenance": sample.provenance,
    }


# {
# 責務: [_copy_regularization: copy separately fingerprinted regularization images]
# 処理: [create a dedicated directory and verify each source digest while copying]
# 引数: [stage: export staging directory, images: validated regularization path/digest pairs]
# 戻り値: [list[dict[str, str]]: output path and SHA records]
# }
def _copy_regularization(stage: Path, images: tuple[tuple[Path, str], ...]) -> list[dict[str, str]]:
    if not images:
        return []
    output_dir = stage / "regularization"
    output_dir.mkdir()
    rows = []
    for source, digest in images:
        name = f"{digest[:16]}{source.suffix.casefold()}"
        _copy_verified(source, output_dir / name, digest)
        rows.append({"image": f"regularization/{name}", "sha256": digest})
    return rows


# {
# 責務: [_write_trainer_templates: write starter manifests for supported trainer formats]
# 処理: [save shared JSON metadata and a valid sd-scripts TOML subset configuration]
# 引数: [stage: output staging directory, analysis: curation report, trainer: selected trainer, sample_rows: copied sample rows, regularization_rows: prior image rows]
# 戻り値: [None: templates written]
# }
def _write_trainer_templates(
    stage: Path,
    analysis: DatasetAnalysis,
    trainer: str,
    sample_rows: list[dict[str, object]],
    regularization_rows: list[dict[str, str]],
) -> None:
    manifest = {
        "schema_version": 1,
        "fingerprint": analysis.fingerprint,
        "task": analysis.task.value,
        "base_family": analysis.base_family,
        "trainer": trainer,
        "sample_count": len(sample_rows),
        "train_count": sum(row["split"] == "train" for row in sample_rows),
        "validation_count": sum(row["split"] == "validation" for row in sample_rows),
        "crop_policy": sorted({row["crop_policy"] for row in sample_rows}),
        "coverage": [cell.__dict__ for cell in analysis.coverage],
        "missing_coverage": [cell.__dict__ for cell in analysis.missing_coverage],
        "warnings": list(analysis.warnings),
        "duplicate_groups": [
            {"id": group_id, "images": [path.name for path in paths]}
            for group_id, paths in analysis.duplicate_groups
        ],
        "regularization": regularization_rows,
        "samples": sample_rows,
    }
    _write_json(stage / "dataset_manifest.json", manifest)
    trainer_config = {
        "schema_version": 1,
        "trainer": trainer,
        "dataset_manifest": "dataset_manifest.json",
        "train_data_dir": "train",
        "validation_data_dir": "validation",
        "caption_file_extension": ".txt",
        "regularization_data_dir": "regularization" if regularization_rows else None,
        "crop_policy": sorted({row["crop_policy"] for row in sample_rows}),
        "sample_weight_manifest_field": "samples[].sample_weight",
        "image_size": "use trainer bucket/resolution settings for the selected base model",
    }
    _write_json(stage / "trainer_dataset_config.json", trainer_config)
    if trainer == "sd-scripts":
        config_text = (
            "[general]\n"
            "enable_bucket = true\n"
            "shuffle_caption = false\n"
            'caption_extension = ".txt"\n\n'
            "[[datasets]]\n"
            "resolution = 1024\n"
            "batch_size = 1\n\n"
            "[[datasets.subsets]]\n"
            'image_dir = "train"\n'
            "num_repeats = 1\n"
        )
        (stage / "sd_scripts_dataset.toml").write_text(config_text, encoding="utf-8")
    if trainer in {"simpletuner", "ai-toolkit"}:
        _write_json(stage / f"{trainer.replace('-', '_')}_dataset.json", trainer_config)


# {
# 責務: [export_dataset: create a trainer-neutral dataset tree and import templates]
# 処理: [copy selected files into an isolated staging directory, write captions/manifest/templates, then atomically publish the new directory]
# 引数: [analysis: curation plan, destination: new output directory, trainer: supported trainer identifier]
# 戻り値: [Path: committed export directory]
# エラー: [ValueError: destination exists, trainer is unsupported, or dataset contains no usable samples; OSError: staged write/copy failure]
# }
def export_dataset(analysis: DatasetAnalysis, destination: str | Path, trainer: str) -> Path:
    trainer_name = trainer.strip().casefold()
    if trainer_name not in SUPPORTED_TRAINERS:
        raise ValueError(f"unsupported trainer export: {trainer}")
    target = Path(destination).expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError("dataset export destination must not already exist")
    usable = tuple(sample for sample in analysis.samples if sample.action != SampleAction.EXCLUDE)
    if not usable:
        raise ValueError("cannot export a dataset with no included images")
    parent = target.parent.resolve(strict=True)
    final_target = parent / target.name
    if not target.name or final_target.exists() or final_target.is_symlink():
        raise FileExistsError("dataset export destination already exists or is invalid")
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.stage-", dir=parent))
    try:
        (stage / "train").mkdir()
        (stage / "validation").mkdir()
        occurrences: dict[tuple[str, str], int] = {}
        sample_rows = []
        for sample in usable:
            split = sample.split if sample.split in {"train", "validation"} else "train"
            key = (split, sample.features.sha256)
            occurrence = occurrences.get(key, 0)
            occurrences[key] = occurrence + 1
            sample_rows.append(_copy_sample(stage, sample, occurrence))
        regularization_rows = _copy_regularization(stage, analysis.regularization_images)
        _write_trainer_templates(stage, analysis, trainer_name, sample_rows, regularization_rows)
        os.rename(stage, final_target)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return final_target
