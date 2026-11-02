"""Typed capture-session data contracts with source provenance."""

from __future__ import annotations

import math
from dataclasses import dataclass


# {
#   責務: [CaptureFrame: one captured RGB/RAW observation and source metadataを保持する]
#   フィールド: [relative_path, payload, media_type, capture_time, exposure_ev, iso, aperture, polarization_angle, sha256]
# }
@dataclass(frozen=True, slots=True)
class CaptureFrame:
    relative_path: str
    payload: bytes
    media_type: str
    source_format: str
    sha256: str
    capture_time: str = ""
    exposure_ev: float | None = None
    iso: int | None = None
    aperture: float | None = None
    polarization_angle: float | None = None

    # {
    #   責務: [__post_init__: frame payload and optional EXIF-like metadataを検証する]
    #   処理: [reject empty evidence and non-finite metadata]
    #   引数: [self: immutable imported frame]
    #   戻り値: []
    #   エラー: [TypeError or ValueError: malformed frame]
    # }
    def __post_init__(self) -> None:
        if not self.relative_path or not self.payload or not self.sha256:
            raise ValueError("capture frame requires a path, payload, and digest")
        if self.media_type not in {"image", "raw"}:
            raise ValueError("capture media_type must be image or raw")
        for name, value in (
            ("exposure_ev", self.exposure_ev),
            ("aperture", self.aperture),
            ("polarization_angle", self.polarization_angle),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number")
        if self.iso is not None and (
            isinstance(self.iso, bool) or not isinstance(self.iso, int) or self.iso < 1
        ):
            raise ValueError("ISO must be a positive integer")


# {
#   責務: [CaptureQuality: measurable frame quality metricsを表す]
#   フィールド: [relative_path, score, blur_proxy, clipped_fraction, warnings]
# }
@dataclass(frozen=True, slots=True)
class CaptureQuality:
    relative_path: str
    score: float
    blur_proxy: float
    clipped_fraction: float
    warnings: tuple[str, ...] = ()

    # {
    #   責務: [__post_init__: normalized quality metricsをvalidateする]
    #   処理: [require finite normalized score and clipping fraction]
    #   引数: [self: one frame quality report]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        for name, value in (
            ("score", self.score),
            ("blur_proxy", self.blur_proxy),
            ("clipped_fraction", self.clipped_fraction),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (float, int))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number")
        if not 0 <= self.score <= 1 or not 0 <= self.clipped_fraction <= 1 or self.blur_proxy < 0:
            raise ValueError("capture quality metrics are outside supported ranges")


# {
#   責務: [CaptureSet: one local burst/bracket/polarization sessionとprovenanceを保持する]
#   フィールド: [capture_set_id, frames, created_at, source]
# }
@dataclass(frozen=True, slots=True)
class CaptureSet:
    capture_set_id: str
    frames: tuple[CaptureFrame, ...]
    created_at: str = ""
    source: str = "local_import"
    aligned_frames_assumed: bool = False

    # {
    #   責務: [__post_init__: capture session identity and frame uniquenessを検証する]
    #   処理: [preserve at least one uniquely named observed frame]
    #   引数: [self: imported capture session]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.capture_set_id.strip() or not self.frames:
            raise ValueError("capture set requires an ID and at least one frame")
        paths = [frame.relative_path for frame in self.frames]
        if len(paths) != len(set(paths)):
            raise ValueError("capture set frame paths must be unique")

    # {
    #   責務: [is_burst: multi-observation setかを判定する]
    #   処理: [require at least three frames for burst processing]
    #   引数: [self: capture session]
    #   戻り値: [bool: enough frames for burst analysis]
    # }
    @property
    def is_burst(self) -> bool:
        return len(self.frames) >= 3

    # {
    #   責務: [has_exposure_bracket: exposure metadataの複数値を確認する]
    #   処理: [report bracket availability only when at least two explicit exposure values differ]
    #   引数: [self: capture session]
    #   戻り値: [bool: exposure bracket metadata is present]
    # }
    @property
    def has_exposure_bracket(self) -> bool:
        values = {frame.exposure_ev for frame in self.frames if frame.exposure_ev is not None}
        return len(values) >= 2

    # {
    #   責務: [has_polarization: polarizer angle metadataの存在を確認する]
    #   処理: [count only explicit polarization observations]
    #   引数: [self: capture session]
    #   戻り値: [bool: any polarized observations are present]
    # }
    @property
    def has_polarization(self) -> bool:
        return any(frame.polarization_angle is not None for frame in self.frames)
