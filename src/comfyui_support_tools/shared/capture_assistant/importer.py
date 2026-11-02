"""Safe local folder importer for capture sets and optional capture manifests."""

from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image

from .contracts import CaptureFrame, CaptureSet

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_RAW_SUFFIXES = {".dng", ".nef", ".cr2", ".cr3", ".arw", ".raf", ".orf", ".rw2"}
_MANIFEST_NAME = "capture-set.json"
_MAX_CAPTURE_SET_BYTES = 512 * 1024 * 1024


# {
#   責務: [CaptureSetImporter: local folderとoptional metadata manifestをCaptureSetへ変換する]
#   フィールド: [16MP/frame and 512 frame bounds]
#   処理: [reject traversal and external symlinks, preserve raw bytes and original hashes]
# }
class CaptureSetImporter:
    # {
    #   責務: [load_video: local short videoから選択範囲のdecoded framesをCaptureSetへ変換する]
    #   処理: [decode selected frame indices, retain video digest and encode per-frame RGB PNG payloads]
    #   引数: [path: local video, start_frame: inclusive index, end_frame: exclusive index, frame_step: sampling interval]
    #   戻り値: [CaptureSet: bounded frame observations with source provenance]
    #   エラー: [OSError or ValueError: unsupported video, invalid range, or resource cap]
    # }
    def load_video(
        self,
        path: Path,
        start_frame: int = 0,
        end_frame: int | None = None,
        frame_step: int = 1,
    ) -> CaptureSet:
        import cv2

        video_path = Path(path).resolve(strict=True)
        if not video_path.is_file() or video_path.stat().st_size > _MAX_CAPTURE_SET_BYTES:
            raise ValueError("video input must be a local file smaller than 512 megabytes")
        if (
            isinstance(start_frame, bool)
            or not isinstance(start_frame, int)
            or isinstance(frame_step, bool)
            or not isinstance(frame_step, int)
            or frame_step < 1
        ):
            raise ValueError("video frame range requires non-negative integer indices and step")
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            capture.release()
            raise ValueError("could not open local video input")
        try:
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            stop = frame_count if end_frame is None else end_frame
            if (
                frame_count < 1
                or start_frame < 0
                or isinstance(stop, bool)
                or not isinstance(stop, int)
                or stop > frame_count
                or stop - start_frame < 2
            ):
                raise ValueError("video frame range must select at least two available frames")
            selected_indices = tuple(range(start_frame, stop, frame_step))
            if len(selected_indices) < 2:
                raise ValueError("video frame range must select at least two available frames")
            if stop - start_frame > 600:
                raise ValueError("video frame range is limited to 600 frames")
            if len(selected_indices) > 12:
                raise ValueError(
                    "video import is limited to 12 frames; increase frame_step or narrow the range"
                )
            source_digest = _file_sha256(video_path)
            frames = []
            selected = set(selected_indices)
            frame_index = 0
            while frame_index < stop:
                success, bgr = capture.read()
                if not success:
                    raise ValueError(f"video ended before selected frame {frame_index}")
                if frame_index in selected:
                    height, width = bgr.shape[:2]
                    if height * width > 4_000_000:
                        raise ValueError("video frame exceeds the 4-megapixel fusion limit")
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    stream = io.BytesIO()
                    Image.fromarray(rgb, "RGB").save(stream, format="PNG", optimize=True)
                    payload = stream.getvalue()
                    frames.append(
                        CaptureFrame(
                            relative_path=f"{video_path.name}@frame-{frame_index:06d}.png",
                            payload=payload,
                            media_type="image",
                            source_format="video_frame_png",
                            sha256=hashlib.sha256(payload).hexdigest(),
                            capture_time=(
                                f"PT{frame_index / fps:.6f}S"
                                if math.isfinite(fps) and fps > 0
                                else ""
                            ),
                        )
                    )
                frame_index += 1
            return CaptureSet(
                video_path.stem,
                tuple(frames),
                source=f"video:{video_path.name}:{source_digest}",
            )
        finally:
            capture.release()

    # {
    #   責務: [load: capture folderからimage/raw observationsとmetadataを読み込む]
    #   処理: [read local files only, apply EXIF orientation for image validation, verify optional manifest]
    #   引数: [directory: local capture folder]
    #   戻り値: [CaptureSet: immutable ordered observations]
    #   エラー: [OSError or ValueError: unsafe, invalid, or empty capture set]
    # }
    def load(self, directory: Path) -> CaptureSet:
        root = Path(directory).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("capture-set source must be a directory")
        manifest = _read_manifest(root / _MANIFEST_NAME)
        metadata_by_path = {row["path"]: row for row in manifest.get("frames", [])}
        paths = sorted(
            path
            for path in root.iterdir()
            if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES | _RAW_SUFFIXES
        )
        if not paths or len(paths) > 512:
            raise ValueError("capture set must contain between 1 and 512 supported frame files")
        if sum(path.stat().st_size for path in paths) > _MAX_CAPTURE_SET_BYTES:
            raise ValueError("capture set exceeds the 512-megabyte import budget")
        frames = []
        for path in paths:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError(f"capture frame resolves outside the selected folder: {path.name}")
            payload = resolved.read_bytes()
            metadata = metadata_by_path.get(path.name, {})
            raw = path.suffix.lower() in _RAW_SUFFIXES
            exif = {} if raw else _read_exif_metadata(payload)
            frames.append(
                CaptureFrame(
                    relative_path=path.name,
                    payload=payload,
                    media_type="raw" if raw else "image",
                    source_format=path.suffix.lower().lstrip("."),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    capture_time=str(metadata.get("capture_time", exif.get("capture_time", ""))),
                    exposure_ev=_number(metadata.get("exposure_ev", exif.get("exposure_ev"))),
                    iso=_integer(metadata.get("iso", exif.get("iso"))),
                    aperture=_number(metadata.get("aperture", exif.get("aperture"))),
                    polarization_angle=_number(metadata.get("polarization_angle")),
                )
            )
        return CaptureSet(
            str(manifest.get("capture_set_id") or root.name),
            tuple(frames),
            str(manifest.get("created_at", "")),
            aligned_frames_assumed=manifest.get("aligned_frames_assumed") is True,
        )


# {
#   責務: [_read_manifest: optional manifest JSONをschemaとpath規則に沿って読む]
#   処理: [support capture-set.v1 and reject path separators/traversal in frame references]
#   引数: [path: manifest file path]
#   戻り値: [dict[str, object]: validated manifest values]
# }
def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("capture-set manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict) or value.get("schema") != "capture-set.v1":
        raise ValueError("capture-set manifest schema must be capture-set.v1")
    rows = value.get("frames", [])
    if not isinstance(rows, list):
        raise ValueError("capture-set manifest frames must be an array")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError("each capture manifest frame requires a path")
        if Path(row["path"]).name != row["path"] or row["path"] in {".", ".."}:
            raise ValueError("capture manifest paths must be local file names")
    return value


# {
#   責務: [_read_exif_metadata: supported image EXIFから撮影情報をsafeな値に変換する]
#   処理: [read capture time, exposure compensation, ISO, and aperture without retaining unrelated EXIF]
#   引数: [payload: encoded image file]
#   戻り値: [dict[str, object]: selected metadata only]
# }
def _read_exif_metadata(payload: bytes) -> dict[str, object]:
    import io

    try:
        with Image.open(io.BytesIO(payload)) as source:
            exif = source.getexif()
        date = exif.get(36867) or exif.get(306) or ""
        exposure_bias = exif.get(37380)
        if hasattr(exposure_bias, "numerator") and exposure_bias.denominator:
            exposure_bias = exposure_bias.numerator / exposure_bias.denominator
        aperture = exif.get(33437)
        if hasattr(aperture, "numerator") and aperture.denominator:
            aperture = aperture.numerator / aperture.denominator
        return {
            "capture_time": str(date),
            "exposure_ev": exposure_bias if isinstance(exposure_bias, (int, float)) else None,
            "iso": exif.get(34855),
            "aperture": aperture if isinstance(aperture, (int, float)) else None,
        }
    except (OSError, ValueError, TypeError):
        return {}


# {
#   責務: [_number: optional metadata fieldをfinite floatへ変換する]
#   処理: [return None for absent or invalid external metadata]
#   引数: [value: JSON or EXIF value]
#   戻り値: [float | None: normalized scalar]
# }
def _number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


# {
#   責務: [_integer: optional ISO metadataをpositive integerへ変換する]
#   処理: [discard malformed values without losing the frame itself]
#   引数: [value: JSON or EXIF value]
#   戻り値: [int | None: normalized ISO]
# }
def _integer(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


# {
#   責務: [_file_sha256: local videoをbounded memoryでhashする]
#   処理: [stream one-megabyte chunks into SHA-256]
#   引数: [path: validated local input file]
#   戻り値: [str: lowercase content digest]
# }
def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
