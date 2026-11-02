"""Backend-neutral data contract for decoded video frames used by analysis."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np


# {
#   責務: [FrameDecodeStatus: frame analysisへ渡す前のdecode/validation状態を定義する]
#   フィールド: [ok、decode_failed、invalid_frame、unsupported_pixel_format、unsupported_color_metadata、corrupted、timestamp_unresolved]
# }
class FrameDecodeStatus(str, Enum):
    OK = "ok"
    DECODE_FAILED = "decode_failed"
    INVALID_FRAME = "invalid_frame"
    UNSUPPORTED_PIXEL_FORMAT = "unsupported_pixel_format"
    UNSUPPORTED_COLOR_METADATA = "unsupported_color_metadata"
    CORRUPTED = "corrupted"
    TIMESTAMP_UNRESOLVED = "timestamp_unresolved"


# {
#   責務: [ActivePictureRect: letterbox/pillarboxを除いた有効映像領域を表す]
#   フィールド: [x、y、width、height]
# }
@dataclass(frozen=True)
class ActivePictureRect:
    x: int
    y: int
    width: int
    height: int


# {
#   責務: [DecodedVideoFrame: video backendのdecode結果を共通正規化層へ渡す]
#   フィールド: [pixels、stream geometry/pixel/color metadata、requested/actual time、PTS/time_base、error]
# }
@dataclass(frozen=True)
class DecodedVideoFrame:
    pixels: np.ndarray | None
    pixel_format: str
    width: int = 0
    height: int = 0
    color_primaries: str = "bt709"
    transfer_function: str = "bt709"
    color_range: str = "full"
    matrix_coefficients: str = "bt709"
    requested_timestamp: float | None = None
    actual_timestamp: float | None = None
    pts: int | None = None
    time_base: Fraction | None = None
    stream_metadata: Mapping[str, str | int | float | bool | None] | None = None
    decode_status: FrameDecodeStatus | str = FrameDecodeStatus.OK
    error: str = ""


# {
#   責務: [VideoFrameDecoder: libav/FFmpeg等decoder adapterの共通呼び出し契約を定義する]
#   フィールド: [decode_frame adapter method]
#   処理: [1: requested timestampを受け取る 2: 共通metadata付きDecodedVideoFrameを返す]
#   引数: [source: 動画source path, requested_timestamp: seek要求時刻]
#   戻り値: [DecodedVideoFrame: actual timingとsource stream metadataを含むdecode結果]
# }
@runtime_checkable
class VideoFrameDecoder(Protocol):
    # {
    #   責務: [decode_frame: requested timestampでsource frameをdecodeする]
    #   処理: [1: source videoの指定時刻frameを読む]
    #   引数: [source: 動画source path, requested_timestamp: requested seek時刻]
    #   戻り値: [decoded: 共通metadata付きdecoded frame]
    # }
    def decode_frame(
        self, source: Path, requested_timestamp: float | None
    ) -> DecodedVideoFrame: ...


# {
#   責務: [FrameAnalysisInput: 検出/OCR/VLMへ渡す解析用canonical frameを保持する]
#   フィールド: [RGB linear float pixels、normalized luminance、active rect、timeline、decode/error metadata]
# }
@dataclass(frozen=True)
class FrameAnalysisInput:
    width: int
    height: int
    pixel_format: str
    source_color_primaries: str
    source_transfer_function: str
    source_color_range: str
    source_matrix_coefficients: str
    canonical_colorspace: str
    canonical_luminance_range: tuple[float, float]
    analysis_rgb: np.ndarray | None
    luminance: np.ndarray | None
    active_picture_rect: ActivePictureRect | None
    requested_timestamp: float | None
    actual_timestamp: float | None
    pts: int | None
    time_base: Fraction | None
    decode_status: FrameDecodeStatus
    stream_metadata: tuple[tuple[str, str | int | float | bool | None], ...]
    error: str = ""

    # {
    #   責務: [has_pixels: analysis planesが利用可能かを返す]
    #   処理: [1: RGB planeとluminance planeの両方の有無を確認する]
    #   引数: []
    #   戻り値: [available: 両planeがある場合true]
    # }
    @property
    def has_pixels(self) -> bool:
        """Return whether the decoded frame contains usable pixel planes."""
        return self.analysis_rgb is not None and self.luminance is not None
