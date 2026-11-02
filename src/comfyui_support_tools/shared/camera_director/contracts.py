"""Contracts for VMD camera planning and rendering adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


# {
# 責務: [CameraStyle: generatorが使えるcamera演出presetを定義する]
# フィールド: [preset names]
# 処理: [距離・cut・motion strategy選択に利用する]
# }
class CameraStyle(str, Enum):
    IDOL = "idol"
    CINEMATIC = "cinematic"
    ENERGETIC = "energetic"
    CUTE = "cute"
    CALM = "calm"
    DRAMATIC = "dramatic"
    STAGE_FIXED = "stage-fixed"
    CLOSE_UP_HEAVY = "close-up-heavy"
    WIDE_SHOT_HEAVY = "wide-shot-heavy"


# {
# 責務: [MotionKey: VMD bone trackのkeyframeを表現する]
# フィールド: [bone, frame, translation]
# 処理: [motion saliency計算とroot trackingに渡す]
# }
@dataclass(frozen=True)
class MotionKey:
    bone: str
    frame: int
    position: tuple[float, float, float]


# {
# 責務: [DanceMotion: VMDから抽出したmotion概要を保持する]
# フィールド: [source, keys, duration]
# 処理: [framing plannerに入力する]
# }
@dataclass(frozen=True)
class DanceMotion:
    source: Path
    keys: tuple[MotionKey, ...]
    duration_frames: int
    fps: int = 30


# {
# 責務: [MusicSection: optional audio区間を時間範囲で表す]
# フィールド: [start, end, intensity, label]
# 処理: [motion shot構成へ同期する]
# }
@dataclass(frozen=True)
class MusicSection:
    start_frame: int
    end_frame: int
    intensity: float
    label: str = "section"


# {
# 責務: [StageBounds: stageとsubjectの安全な範囲を表現する]
# フィールド: [minimum, maximum, subject radius]
# 処理: [camera targetとframing制約を計算する]
# }
@dataclass(frozen=True)
class StageBounds:
    minimum: tuple[float, float, float] = (-10.0, 0.0, -10.0)
    maximum: tuple[float, float, float] = (10.0, 20.0, 10.0)
    subject_radius: float = 1.0


# {
# 責務: [CameraKey: VMD camera keyframeを表す]
# フィールド: [frame, distance, position, rotation, fov, perspective]
# 処理: [VMD exportとpreviewに利用する]
# }
@dataclass(frozen=True)
class CameraKey:
    frame: int
    distance: float
    position: tuple[float, float, float]
    rotation: tuple[float, float, float]
    field_of_view: int = 30
    perspective: bool = True


# {
# 責務: [CameraFinding: visibility/collision quality issueを記録する]
# フィールド: [frame, code, severity, message]
# 処理: [plan reportで修正箇所を指し示す]
# }
@dataclass(frozen=True)
class CameraFinding:
    frame: int
    code: str
    severity: str
    message: str


# {
# 責務: [CameraPlan: camera keysと検査結果を束ねる]
# フィールド: [keys, style, sections, findings, seed]
# 処理: [VMD/plan/previewを一貫してexportする]
# }
@dataclass(frozen=True)
class CameraPlan:
    keys: tuple[CameraKey, ...]
    style: CameraStyle
    sections: tuple[MusicSection, ...]
    findings: tuple[CameraFinding, ...]
    seed: int


# {
# 責務: [CameraBackend: research modelとの拡張境界を定義する]
# フィールド: [plan callable]
# 処理: [DanceStyleCam等のbackendをinjectionする]
# }
class CameraBackend(Protocol):
    # {
    # 責務: [generate: camera plan候補を生成する]
    # 処理: [motion/music/boundsをbackendへ渡しcamera keyを返す]
    # 引数: [motion, style, sections, bounds, seed: planning入力]
    # 戻り値: [tuple[CameraKey, ...]: camera keyframes]
    # }
    def generate(
        self,
        motion: DanceMotion,
        style: CameraStyle,
        sections: tuple[MusicSection, ...],
        bounds: StageBounds,
        seed: int,
    ) -> tuple[CameraKey, ...]: ...


# {
# 責務: [CameraCollisionChecker: model-aware collision validation adapter]
# フィールド: [check callable]
# 処理: [camera body/stage collisionを検出する]
# }
class CameraCollisionChecker(Protocol):
    # {
    # 責務: [check: camera keyの衝突を検査する]
    # 処理: [PMX/stage backendからfindingを返す]
    # 引数: [key, bounds: camera keyとscene bounds]
    # 戻り値: [tuple[CameraFinding, ...]: collision findings]
    # }
    def check(self, key: CameraKey, bounds: StageBounds) -> tuple[CameraFinding, ...]: ...
