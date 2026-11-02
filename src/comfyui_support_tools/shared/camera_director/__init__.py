"""MMD camera motion planning, VMD I/O, music sections, and artifact export."""

from .adapters import DanceStyleCamAdapter, DanceStyleCamEngine
from .contracts import (
    CameraBackend,
    CameraCollisionChecker,
    CameraFinding,
    CameraKey,
    CameraPlan,
    CameraStyle,
    DanceMotion,
    MotionKey,
    MusicSection,
    StageBounds,
)
from .planning import (
    HeuristicCameraBackend,
    WavSectionError,
    analyze_wav_sections,
    plan_camera,
    reroll_camera_section,
    validate_camera_keys,
)
from .preview import render_camera_preview
from .service import CameraArtifacts, build_camera_plan, export_camera_plan
from .vmd import VmdFormatError, read_dance_vmd, write_camera_vmd

__all__ = [
    "CameraArtifacts",
    "CameraBackend",
    "CameraCollisionChecker",
    "DanceStyleCamAdapter",
    "DanceStyleCamEngine",
    "CameraFinding",
    "CameraKey",
    "CameraPlan",
    "CameraStyle",
    "DanceMotion",
    "HeuristicCameraBackend",
    "MotionKey",
    "MusicSection",
    "StageBounds",
    "VmdFormatError",
    "WavSectionError",
    "analyze_wav_sections",
    "build_camera_plan",
    "export_camera_plan",
    "plan_camera",
    "read_dance_vmd",
    "render_camera_preview",
    "reroll_camera_section",
    "validate_camera_keys",
    "write_camera_vmd",
]
