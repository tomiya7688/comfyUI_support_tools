"""Run a pose backend and produce auditable VMD motion artifacts."""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from .contracts import PoseRecoveryBackend, RetargetProfile, VideoMotionReport
from .processing import process_recovered_motion
from .vmd import write_motion_vmd


# {
# 責務: [convert_video_to_vmd: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def convert_video_to_vmd(
    video_path: Path,
    output_dir: Path,
    backend: PoseRecoveryBackend,
    profile: RetargetProfile,
    *,
    person_id: str | None = None,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> VideoMotionReport:
    """Recover, clean, serialize, and preview a video motion request."""
    source = Path(video_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if start_frame is not None and start_frame < 0:
        raise ValueError("start_frame must be non-negative")
    if end_frame is not None and (
        end_frame < 0 or (start_frame is not None and end_frame < start_frame)
    ):
        raise ValueError("end_frame must be >= start_frame and non-negative")
    recovered = backend.recover(source, person_id, start_frame, end_frame)
    keys, confidence, findings = process_recovered_motion(recovered, profile)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    stem = source.stem or "motion"
    paths = (
        destination / f"{stem}.vmd",
        destination / f"{stem}.motion.json",
        destination / f"{stem}.preview.gif",
    )
    _write_artifacts(
        paths,
        (
            write_motion_vmd(keys, profile.model_name),
            _report_bytes(recovered.fps, keys, confidence, findings),
            _preview_bytes(keys),
        ),
    )
    return VideoMotionReport(recovered.fps, keys, confidence, findings, *paths)


# {
# 責務: [_report_bytes: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _report_bytes(fps, keys, confidence, findings) -> bytes:
    report = {
        "schema_version": 1,
        "fps": fps,
        "key_count": len(keys),
        "confidence": [
            {"frame": frame, "bone": bone, "score": score} for frame, bone, score in confidence
        ],
        "findings": [
            {
                "frame": item.frame,
                "bone": item.bone,
                "code": item.code,
                "severity": item.severity,
                "message": item.message,
            }
            for item in findings
        ],
        "preview_note": "2D mapped-bone motion preview; target PMX geometry and IK are not evaluated.",
    }
    return (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
        "utf-8"
    )


# {
# 責務: [_preview_bytes: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _preview_bytes(keys) -> bytes:
    by_frame = {}
    for key in keys:
        by_frame.setdefault(key.frame, {})[key.bone] = key.translation
    frames = sorted(by_frame)
    if not frames:
        raise ValueError("cannot preview empty motion")
    # GIF bounds and frame count are capped to keep untrusted recovery output manageable.
    selected = frames[:: max(1, math.ceil(len(frames) / 120))][:120]
    images = []
    colors = ((38, 112, 207), (230, 91, 58), (54, 160, 100), (170, 84, 180))
    for frame_number in selected:
        pose = by_frame[frame_number]
        points = list(pose.values())
        if not points:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        scale = min(160 / max(max_x - min_x, 0.1), 220 / max(max_y - min_y, 0.1))
        image = Image.new("RGB", (320, 280), "white")
        draw = ImageDraw.Draw(image)
        screen = {
            name: (160 + (point[0] - (min_x + max_x) / 2) * scale, 245 - (point[1] - min_y) * scale)
            for name, point in pose.items()
        }
        ordered = sorted(screen.items())
        for index, (_name, point) in enumerate(ordered):
            if index:
                draw.line((ordered[index - 1][1], point), fill=(125, 125, 125), width=3)
            draw.ellipse(
                (point[0] - 5, point[1] - 5, point[0] + 5, point[1] + 5),
                fill=colors[index % len(colors)],
            )
        draw.text((8, 8), f"Frame {frame_number} | mapped bones", fill="black")
        images.append(image)
    if not images:
        raise ValueError("cannot preview motion without mapped bone points")
    import io

    stream = io.BytesIO()
    images[0].save(
        stream,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=80,
        loop=0,
        optimize=True,
    )
    return stream.getvalue()


# {
# 責務: [_write_artifacts: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _write_artifacts(paths: tuple[Path, ...], contents: tuple[bytes, ...]) -> None:
    reserved = []
    temporaries = []
    try:
        for path in paths:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            reserved.append(path)
        for path, content in zip(paths, contents, strict=True):
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as handle:
                handle.write(content)
                temporaries.append(Path(handle.name))
        for temporary, path in zip(temporaries, paths, strict=True):
            os.replace(temporary, path)
        temporaries.clear()
    except BaseException:
        for path in reserved:
            path.unlink(missing_ok=True)
        raise
    finally:
        for path in temporaries:
            path.unlink(missing_ok=True)
