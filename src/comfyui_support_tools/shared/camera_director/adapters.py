"""Optional adapters for external camera-generation research backends."""

from __future__ import annotations

from typing import Protocol

from .contracts import CameraKey, CameraStyle, DanceMotion, MusicSection, StageBounds


# {
# 責務: [DanceStyleCamEngine: external DanceStyleCam callable interface]
# フィールド: [generate_camera_keys callable]
# 処理: [research implementationをcamera domainから分離する]
# }
class DanceStyleCamEngine(Protocol):
    # {
    # 責務: [generate_camera_keys: external modelでcamera keysを生成する]
    # 処理: [VMD motion conditionとstyleを受けてkey候補を返す]
    # 引数: [motion, style, sections, bounds, seed: inference inputs]
    # 戻り値: [tuple[CameraKey, ...]: generated keys]
    # }
    def generate_camera_keys(
        self,
        motion: DanceMotion,
        style: CameraStyle,
        sections: tuple[MusicSection, ...],
        bounds: StageBounds,
        seed: int,
    ) -> tuple[CameraKey, ...]: ...


# {
# 責務: [DanceStyleCamAdapter: DanceStyleCam engineをCameraBackend contractへ適合する]
# フィールド: [engine]
# 処理: [external research backendを差替可能にする]
# }
class DanceStyleCamAdapter:
    # {
    # 責務: [__init__: external engineを保持する]
    # 処理: [injected engineをadapterへ束縛する]
    # 引数: [engine: camera generation engine]
    # 戻り値: [None: なし]
    # }
    def __init__(self, engine: DanceStyleCamEngine) -> None:
        self.engine = engine

    # {
    # 責務: [generate: external DanceStyleCam engineへrequestを渡す]
    # 処理: [camera plan inputsをそのままengineへ転送する]
    # 引数: [motion, style, sections, bounds, seed: planning inputs]
    # 戻り値: [tuple[CameraKey, ...]: generated keys]
    # }
    def generate(
        self,
        motion: DanceMotion,
        style: CameraStyle,
        sections: tuple[MusicSection, ...],
        bounds: StageBounds,
        seed: int,
    ) -> tuple[CameraKey, ...]:
        return self.engine.generate_camera_keys(motion, style, sections, bounds, seed)
