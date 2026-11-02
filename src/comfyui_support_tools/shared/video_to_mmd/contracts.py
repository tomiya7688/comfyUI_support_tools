"""Typed motion-capture results and recovery/retarget extension contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


# {
# 責務: [SourceBonePose: recovery backendの3D bone transformを保持する]
# フィールド: [name, translation, rotation, confidence, contact]
# 処理: [MMD skeletonへのretargetとcleanupへ渡す]
# }
@dataclass(frozen=True)
class SourceBonePose:
    name: str
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    confidence: float
    foot_contact: bool = False


# {
# 責務: [RecoveredFrame: timestamp付きrecovery骨姿勢を表す]
# フィールド: [frame, person_id, camera_translation, ground_height, bones]
# 処理: [camera compensationとperson selectionを可能にする]
# }
@dataclass(frozen=True)
class RecoveredFrame:
    frame: int
    person_id: str
    camera_translation: tuple[float, float, float]
    ground_height: float
    bones: tuple[SourceBonePose, ...]


# {
# 責務: [RecoveredMotion: 3D pose backendのfps/frame列を束ねる]
# フィールド: [fps, frames, camera_compensated]
# 処理: [backend間で統一したmotion contractを提供する]
# }
@dataclass(frozen=True)
class RecoveredMotion:
    fps: int
    frames: tuple[RecoveredFrame, ...]
    camera_compensated: bool = False


# {
# 責務: [RetargetRule: source boneをtarget MMD boneへ写像する]
# フィールド: [source, target, translation scale, axis/sign]
# 処理: [rest-pose fit後のcoordinate mappingを構成する]
# }
@dataclass(frozen=True)
class RetargetRule:
    source_name: str
    target_name: str
    translation_scale: float = 1.0
    position_axis: tuple[int, int, int] = (0, 1, 2)
    position_sign: tuple[float, float, float] = (1.0, 1.0, 1.0)


# {
# 責務: [RetargetProfile: target PMX向けskeleton mappingを保持する]
# フィールド: [model_name, rules, smoothing, key error tolerance]
# 処理: [custom bone mappingとkeyframe reductionを行う]
# }
@dataclass(frozen=True)
class RetargetProfile:
    model_name: str
    rules: tuple[RetargetRule, ...]
    smoothing: float = 0.25
    key_error_tolerance: float = 0.01
    maximum_speed: float = 12.0


# {
# 責務: [VmdBoneKey: VMD target bone keyframeを表現する]
# フィールド: [bone, frame, translation, quaternion]
# 処理: [VMD serializationとpreviewへ渡す]
# }
@dataclass(frozen=True)
class VmdBoneKey:
    bone: str
    frame: int
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]


# {
# 責務: [MotionFinding: low confidence/cleanup riskを伝える]
# フィールド: [frame, bone, code, severity, message]
# 処理: [confidence timelineとrepair reviewに利用する]
# }
@dataclass(frozen=True)
class MotionFinding:
    frame: int
    bone: str
    code: str
    severity: str
    message: str


# {
# 責務: [VideoMotionReport: VMDとquality/preview outputsを束ねる]
# フィールド: [keys, confidence, findings, output paths]
# 処理: [generated motionをauditableに返す]
# }
@dataclass(frozen=True)
class VideoMotionReport:
    fps: int
    keys: tuple[VmdBoneKey, ...]
    confidence: tuple[tuple[int, str, float], ...]
    findings: tuple[MotionFinding, ...]
    vmd_path: Path
    report_path: Path
    preview_path: Path


# {
# 責務: [PoseRecoveryBackend: GVHMR/WHAM/DWPose runtime adapter]
# フィールド: [recover callable]
# 処理: [外部CV modelをvideo motion coreから分離する]
# }
class PoseRecoveryBackend(Protocol):
    # {
    # 責務: [recover: video区間からtracked 3D pose frameを推定する]
    # 処理: [person id/segment指定でmotion recoveryを実行する]
    # 引数: [video_path, person_id, start_frame, end_frame: video inference request]
    # 戻り値: [RecoveredMotion: confidence付き3D pose sequence]
    # }
    def recover(
        self,
        video_path: Path,
        person_id: str | None = None,
        start_frame: int | None = None,
        end_frame: int | None = None,
    ) -> RecoveredMotion: ...
