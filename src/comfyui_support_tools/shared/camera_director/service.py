"""Camera Director orchestration and non-overwriting artifact export."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from .contracts import (
    CameraBackend,
    CameraCollisionChecker,
    CameraPlan,
    CameraStyle,
    DanceMotion,
    MusicSection,
    StageBounds,
)
from .planning import plan_camera
from .preview import render_camera_preview
from .vmd import write_camera_vmd


# {
# 責務: [CameraArtifacts: export済みVMD/plan/preview pathsを返す]
# フィールド: [vmd, plan, preview, storyboard]
# 処理: [関連artifactsを利用元へ伝える]
# }
@dataclass(frozen=True)
class CameraArtifacts:
    vmd_path: Path
    plan_path: Path
    preview_path: Path
    storyboard_path: Path


# {
# 責務: [build_camera_plan: camera planning stagesをorchestrateする]
# 処理: [1: backendでkey生成, 2: validation/checkerを実行しplanを構築する]
# 引数: [motion, style, bounds, sections, seed, backend, collision_checker: plan inputs]
# 戻り値: [CameraPlan: validated camera plan]
# }
def build_camera_plan(
    motion: DanceMotion,
    style: CameraStyle,
    bounds: StageBounds | None = None,
    sections: tuple[MusicSection, ...] = (),
    seed: int = 0,
    backend: CameraBackend | None = None,
    collision_checker: CameraCollisionChecker | None = None,
) -> CameraPlan:
    bounds = bounds or StageBounds()
    keys, findings = plan_camera(motion, style, bounds, sections, seed, backend, collision_checker)
    return CameraPlan(keys, style, sections, findings, seed)


# {
# 責務: [export_camera_plan: VMD/JSON/SVG artifactsをnon-overwrite保存する]
# 処理: [serializeしてatomic publishする]
# 引数: [plan, output_path: camera planとVMD destination]
# 戻り値: [CameraArtifacts: 作成したartifact paths]
# }
def export_camera_plan(plan: CameraPlan, output_path: str | Path) -> CameraArtifacts:
    destination = Path(output_path).expanduser().resolve()
    if destination.suffix.casefold() != ".vmd":
        raise ValueError("camera output path must end in .vmd")
    plan_path = destination.with_suffix(".camera.json")
    preview_path = destination.with_suffix(".preview.gif")
    storyboard_path = destination.with_suffix(".preview.svg")
    artifacts = {
        destination: write_camera_vmd(plan.keys),
        plan_path: _plan_json(plan),
        preview_path: render_camera_preview(plan),
        storyboard_path: _preview_svg(plan),
    }
    _atomic_write_new_many(artifacts)
    return CameraArtifacts(destination, plan_path, preview_path, storyboard_path)


# {
# 責務: [_plan_json: camera planをJSONへserializeする]
# 処理: [style, keys, sections, findingsをJSON形式にする]
# 引数: [plan: camera plan]
# 戻り値: [bytes: utf-8 JSON]
# }
def _plan_json(plan: CameraPlan) -> bytes:
    payload = {
        "style": plan.style.value,
        "seed": plan.seed,
        "sections": [asdict(section) for section in plan.sections],
        "findings": [asdict(finding) for finding in plan.findings],
        "keys": [asdict(key) for key in plan.keys],
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


# {
# 責務: [_preview_svg: camera plan timelineのSVG previewを作る]
# 処理: [distance variationをtime seriesとして描画する]
# 引数: [plan: camera plan]
# 戻り値: [bytes: SVG data]
# }
def _preview_svg(plan: CameraPlan) -> bytes:
    width, height, padding = 960, 240, 32
    end_frame = max((key.frame for key in plan.keys), default=0)
    points = []
    for key in plan.keys:
        x = padding + (width - 2 * padding) * key.frame / max(end_frame, 1)
        y = padding + (height - 2 * padding) * (1 - min(key.distance, 30.0) / 30.0)
        points.append(f"{x:.1f},{y:.1f}")
    polyline = " ".join(points)
    markers = "".join(
        f'<circle cx="{padding + (width - 2 * padding) * key.frame / max(end_frame, 1):.1f}" '
        f'cy="{padding + (height - 2 * padding) * (1 - min(key.distance, 30.0) / 30.0):.1f}" r="4" />'
        for key in plan.keys
    )
    label = escape(f"{plan.style.value} camera plan · {len(plan.keys)} keys · {end_frame} frames")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="#171923"/><text x="{padding}" y="22" fill="white">{label}</text>'
        f'<line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" stroke="#667085"/>'
        f'<polyline points="{polyline}" fill="none" stroke="#85d7ff" stroke-width="3"/>'
        f'<g fill="#ffd166">{markers}</g></svg>'
    )
    return (svg + "\n").encode("utf-8")


# {
# 責務: [_atomic_write_new_many: artifact一式を上書きなしでpublishする]
# 処理: [1: temp fileへfsync, 2: hardlink publish, 3: failure時cleanup]
# 引数: [artifacts: destinationとserialized content]
# 戻り値: [None: なし]
# }
def _atomic_write_new_many(artifacts: dict[Path, bytes]) -> None:
    temporary_paths: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        for destination, data in artifacts.items():
            if destination.exists():
                raise FileExistsError(f"refusing to overwrite {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, name = tempfile.mkstemp(
                prefix=f".{destination.name}.", dir=destination.parent
            )
            temporary = Path(name)
            temporary_paths[destination] = temporary
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        for destination, temporary in temporary_paths.items():
            os.link(temporary, destination)
            published.append(destination)
    except Exception:
        for destination in published:
            destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary in temporary_paths.values():
            temporary.unlink(missing_ok=True)
