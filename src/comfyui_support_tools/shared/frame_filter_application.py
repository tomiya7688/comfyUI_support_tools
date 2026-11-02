"""Apply low-information analysis to existing image folders without changing sources."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

from comfyui_support_tools.shared.contracts.frame_analysis import (
    DecodedVideoFrame,
    FrameAnalysisInput,
    FrameDecodeStatus,
)
from comfyui_support_tools.shared.contracts.frame_filter import (
    FrameFilterAction,
    FrameFilterBatchManifest,
    FrameFilterDecision,
    FrameFilterOptions,
    FrameFilterReport,
    FrameTextBox,
)
from comfyui_support_tools.shared.output_artifact import ConflictPolicy, atomic_write_bytes
from comfyui_support_tools.shared.video_frame_filter import analyze_frame_sequence
from comfyui_support_tools.shared.video_frame_normalization import normalize_decoded_frame

IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
MAX_ANALYSIS_PIXELS = 40_000_000
MAX_ANALYSIS_SIDE = 2048


# {
#   責務: [filter_existing_frame_folder: image folderを分析し非破壊copy/manifest planを作成する]
#   処理: [1: source/output境界とfilesを検証する 2: directory単位でtemporal分析する 3: dry-runまたはatomic copyする]
#   引数: [input_root: frame source, output_root: separate copy destination, options: filter config, dry_run: preview only, text_detector: optional OCR adapter]
#   戻り値: [FrameFilterBatchManifest: stable per-image report and count summary]
# }
def filter_existing_frame_folder(
    input_root: Path,
    output_root: Path,
    options: FrameFilterOptions,
    *,
    dry_run: bool = True,
    text_detector: Callable[[np.ndarray], Sequence[FrameTextBox]] | None = None,
) -> FrameFilterBatchManifest:
    source = Path(input_root).expanduser().resolve(strict=True)
    requested_destination = Path(output_root).expanduser().absolute()
    if requested_destination.is_symlink():
        raise ValueError("frame filter output cannot be a symbolic link")
    destination = requested_destination.resolve()
    if not source.is_dir():
        raise ValueError("frame input must be a directory")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("frame filter output must be separate from the input tree")
    if not dry_run and options.enabled and (destination.exists() or destination.is_symlink()):
        raise FileExistsError(destination)
    files = _image_files(source)
    if not files:
        raise ValueError("frame input contains no supported image files")
    if options.enabled and (options.detect_text_only or options.detect_title_credits):
        if text_detector is None:
            raise ValueError("text-only/title filtering requires a configured OCR detector")
    grouped: dict[Path, list[Path]] = defaultdict(list)
    for path in files:
        grouped[path.parent].append(path)

    reports = []
    planned_copies: list[tuple[Path, Path]] = []
    for parent, entries in sorted(grouped.items(), key=lambda item: item[0].as_posix()):
        for center_index, path in enumerate(entries):
            first_index = max(0, center_index - 1)
            end_index = min(len(entries), center_index + 2)
            window = entries[first_index:end_index]
            loaded = [
                _load_frame(item, text_detector if index == center_index else None)
                for index, item in enumerate(window, start=first_index)
            ]
            normalized = tuple(item[0] for item in loaded)
            center_offset = center_index - first_index
            boxes = loaded[center_offset][1]
            box_map = {center_offset: boxes} if text_detector is not None else {}
            batch = analyze_frame_sequence(
                parent.relative_to(source).as_posix() or ".",
                normalized,
                options,
                text_boxes=box_map,
            )
            report = batch.reports[center_offset]
            relative = path.relative_to(source)
            detector_version = (
                str(getattr(text_detector, "version", "custom"))
                if text_detector is not None
                else "none"
            )
            report = replace(
                report,
                frame_index=len(reports),
                provenance=report.provenance
                + (
                    ("source_relative_path", relative.as_posix()),
                    ("ocr_engine", detector_version),
                ),
            )
            reports.append(report)
            output_relative = _output_relative_path(relative, report, options)
            if output_relative is not None:
                planned_copies.append((path, destination / output_relative))

    manifest = FrameFilterBatchManifest(
        source.name,
        options,
        tuple(reports),
        sum(item.decision is FrameFilterDecision.KEEP for item in reports),
        sum(item.decision is FrameFilterDecision.DROP for item in reports),
        sum(item.decision is FrameFilterDecision.REVIEW for item in reports),
        sum(item.decision is FrameFilterDecision.ERROR for item in reports),
    )
    if not dry_run and options.enabled:
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
        )
        try:
            staged_copies = [
                (source_path, stage / target.relative_to(destination))
                for source_path, target in planned_copies
            ]
            _apply_copies(staged_copies, source)
            payload = json.dumps(asdict(manifest), ensure_ascii=False, indent=2).encode("utf-8")
            atomic_write_bytes(
                stage / "frame_filter_manifest.json",
                payload,
                policy=ConflictPolicy.FAIL,
                source=source,
            )
            stage.rename(destination)
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    return manifest


# {
#   責務: [_image_files: recursive image inventoryをstable orderで収集しsymlinkを拒否する]
#   処理: [1: tree entriesをsortする 2: source内symlinkを拒否する 3: supported regular imagesだけ返す]
#   引数: [source: resolved input root]
#   戻り値: [files: deterministic supported image list]
# }
def _image_files(source: Path) -> tuple[Path, ...]:
    files = []
    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        if path.is_symlink():
            raise ValueError(f"frame source contains a symlink: {path.relative_to(source)}")
        if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS:
            files.append(path)
    return tuple(files)


# {
#   責務: [_load_frame: still imageをRGBへ読み、shared normalizerとoptional OCRへ渡す]
#   処理: [1: Pillowで安全にdecodeする 2: normalized analysis frameを作る 3: OCR evidenceを検証可能な契約へ正規化する]
#   引数: [path: image source, text_detector: optional analysis callback]
#   戻り値: [frame/pixels/text boxes]
# }
def _load_frame(
    path: Path,
    text_detector: Callable[[np.ndarray], Sequence[FrameTextBox]] | None,
) -> tuple[FrameAnalysisInput, tuple[FrameTextBox, ...]]:
    try:
        with Image.open(path) as image:
            if image.width * image.height > MAX_ANALYSIS_PIXELS:
                raise ValueError("frame exceeds the analysis pixel budget")
            image.load()
            image.thumbnail((MAX_ANALYSIS_SIDE, MAX_ANALYSIS_SIDE), Image.Resampling.LANCZOS)
            pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
        normalized = normalize_decoded_frame(
            DecodedVideoFrame(pixels, "rgb24", actual_timestamp=0.0)
        )
        normalized = replace(normalized, actual_timestamp=None)
    except (OSError, ValueError, UnidentifiedImageError) as error:
        failed = normalize_decoded_frame(
            DecodedVideoFrame(
                None,
                "unknown",
                actual_timestamp=0.0,
                decode_status=FrameDecodeStatus.CORRUPTED,
                error=type(error).__name__,
            )
        )
        return replace(failed, actual_timestamp=None), ()
    boxes = tuple(text_detector(pixels)) if text_detector is not None else ()
    return normalized, boxes


# {
#   責務: [_output_relative_path: decision/actionを非破壊folder layoutへ変換する]
#   処理: [1: keep/drop/review/errorを分類する 2: title/credits separateを専用bucketへ送る]
#   引数: [relative: source relative path, decision: filter result, action: output policy]
#   戻り値: [relative output or None]
# }
def _output_relative_path(
    relative: Path, report: FrameFilterReport, options: FrameFilterOptions
) -> Path | None:
    if options.action is FrameFilterAction.MARK_ONLY:
        return None
    decision = report.decision
    if decision is FrameFilterDecision.KEEP:
        return Path("kept") / relative
    if decision is FrameFilterDecision.ERROR:
        return Path("errors") / relative
    if decision is FrameFilterDecision.REVIEW:
        if options.title_credits_policy == "separate":
            if "credits" in report.reasons:
                return Path("separate") / "credits" / relative
            if "title_card" in report.reasons:
                return Path("separate") / "title_cards" / relative
        return Path("review") / relative
    if options.action is FrameFilterAction.DROP:
        return None
    if options.action is FrameFilterAction.MOVE_TO_REJECTED:
        return Path("rejected") / relative
    if options.action is FrameFilterAction.REVIEW_QUEUE:
        return Path("review") / relative
    return None


# {
#   責務: [_apply_copies: planned outputsを入力を変更せずatomic copyする]
#   処理: [1: copy targetをsource tree外と確認する 2: output conflictを拒否してvalidated bytesをpublishする]
#   引数: [copies: source/target pairs, input_root: source collision boundary]
#   戻り値: []
# }
def _apply_copies(copies: list[tuple[Path, Path]], input_root: Path) -> None:
    targets = [target for _source, target in copies]
    if len(targets) != len(set(targets)):
        raise ValueError("frame filter produced duplicate output paths")
    for target in targets:
        if input_root == target or input_root in target.parents:
            raise ValueError("frame filter copy target overlaps the input tree")
        if target.exists() or target.is_symlink():
            raise FileExistsError(target)
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        atomic_write_bytes(
            target,
            data,
            source=source,
            policy=ConflictPolicy.FAIL,
            validator=lambda staged: _validate_image(staged),
        )


# {
#   責務: [_validate_image: staged copyが元の画像形式でdecodeできることを検証する]
#   処理: [1: Pillowでverifyする 2: corrupted copyをpublish前に拒否する]
#   引数: [path: staged artifact]
#   戻り値: []
# }
def _validate_image(path: Path) -> None:
    with Image.open(path) as image:
        image.verify()
