"""Normalize backend-decoded frames to a shared analysis colorspace."""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np

from comfyui_support_tools.shared.contracts.frame_analysis import (
    ActivePictureRect,
    DecodedVideoFrame,
    FrameAnalysisInput,
    FrameDecodeStatus,
    VideoFrameDecoder,
)

CANONICAL_COLORSPACE = "linear-srgb-d65"
_SUPPORTED_PIXEL_FORMATS = {"rgb24", "bgr24", "rgb48", "bgr48"}
_DARK_THRESHOLD = 0.025
_EDGE_DARK_RATIO = 0.995
_MIN_BAND_PIXELS = 2
_MIN_BAND_FRACTION = 0.015
_MIN_ACTIVE_FRACTION = 0.5

_RGB_TO_XYZ = {
    "bt709": np.array(
        [
            [0.4123908, 0.3575843, 0.1804808],
            [0.2126390, 0.7151687, 0.0721923],
            [0.0193308, 0.1191948, 0.9505322],
        ],
        dtype=np.float32,
    ),
    "bt2020": np.array(
        [
            [0.6369580, 0.1446169, 0.1688810],
            [0.2627002, 0.6779981, 0.0593017],
            [0.0000000, 0.0280727, 1.0609851],
        ],
        dtype=np.float32,
    ),
    "display-p3": np.array(
        [
            [0.4865709, 0.2656677, 0.1982173],
            [0.2289746, 0.6917385, 0.0792869],
            [0.0000000, 0.0451134, 1.0439444],
        ],
        dtype=np.float32,
    ),
}
_XYZ_TO_SRGB = np.linalg.inv(_RGB_TO_XYZ["bt709"])
_SRGB_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


# {
#   責務: [decode_frame_for_analysis: backend decoder境界から同じFrameAnalysisInputを返す]
#   処理: [1: request timestampを検証する 2: adapterを呼ぶ 3: decoder例外をdecode statusに正規化する]
#   引数: [decoder: VideoFrameDecoder adapter, source: 動画file path, requested_timestamp: seek要求時刻]
#   戻り値: [analysis: backendに依存しないFrameAnalysisInput]
# }
def decode_frame_for_analysis(
    decoder: VideoFrameDecoder,
    source: Path,
    requested_timestamp: float | None,
) -> FrameAnalysisInput:
    if requested_timestamp is not None and not math.isfinite(requested_timestamp):
        failed = DecodedVideoFrame(
            None,
            "unknown",
            requested_timestamp=requested_timestamp,
            decode_status=FrameDecodeStatus.INVALID_FRAME,
        )
        return normalize_decoded_frame(failed)
    try:
        decoded = decoder.decode_frame(Path(source), requested_timestamp)
    except Exception as error:
        failed = DecodedVideoFrame(
            None,
            "unknown",
            requested_timestamp=requested_timestamp,
            decode_status=FrameDecodeStatus.DECODE_FAILED,
            error=f"decoder failed: {type(error).__name__}",
        )
        return normalize_decoded_frame(failed)
    if not isinstance(decoded, DecodedVideoFrame):
        failed = DecodedVideoFrame(
            None,
            "unknown",
            requested_timestamp=requested_timestamp,
            decode_status=FrameDecodeStatus.INVALID_FRAME,
            error="decoder returned an invalid frame contract",
        )
        return normalize_decoded_frame(failed)
    if requested_timestamp is not None and decoded.requested_timestamp not in (
        None,
        requested_timestamp,
    ):
        failed = replace(decoded, pixels=None, decode_status=FrameDecodeStatus.INVALID_FRAME)
        return normalize_decoded_frame(failed)
    if requested_timestamp is not None and decoded.requested_timestamp is None:
        decoded = replace(decoded, requested_timestamp=requested_timestamp)
    return normalize_decoded_frame(decoded)


# {
#   責務: [normalize_decoded_frame: backend frameを共通linear-sRGB/luminance contractへ変換する]
#   処理: [1: decoder状態/geometry/timingを検証する 2: pixel rangeとtransferを正規化する 3: primariesを変換しread-only planesを返す]
#   引数: [frame: backend-neutral decoded frame]
#   戻り値: [analysis: 正常化されたFrameAnalysisInputまたは明示的decode error]
# }
def normalize_decoded_frame(frame: DecodedVideoFrame) -> FrameAnalysisInput:
    pixels = frame.pixels
    raw_status = frame.decode_status
    try:
        status = FrameDecodeStatus(raw_status)
    except (TypeError, ValueError):
        status = FrameDecodeStatus.INVALID_FRAME
    try:
        metadata = tuple(sorted((frame.stream_metadata or {}).items()))
    except (AttributeError, TypeError, ValueError):
        metadata = ()
        status = FrameDecodeStatus.INVALID_FRAME
    height, width = (
        pixels.shape[:2]
        if isinstance(pixels, np.ndarray) and pixels.ndim >= 2
        else (frame.height, frame.width)
    )
    actual_timestamp = frame.actual_timestamp
    try:
        if actual_timestamp is None and frame.pts is not None and frame.time_base is not None:
            actual_timestamp = float(frame.pts * frame.time_base)
    except (TypeError, ValueError, OverflowError):
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    if status is not FrameDecodeStatus.OK:
        return _failed(frame, status, width, height, metadata)
    if pixels is None:
        return _failed(frame, FrameDecodeStatus.DECODE_FAILED, width, height, metadata, frame.error)
    if not isinstance(pixels, np.ndarray):
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    if not isinstance(frame.pixel_format, str):
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    if not all(
        isinstance(value, str)
        for value in (
            frame.color_primaries,
            frame.transfer_function,
            frame.color_range,
            frame.matrix_coefficients,
        )
    ):
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    if frame.pixel_format.casefold() not in _SUPPORTED_PIXEL_FORMATS:
        return _failed(frame, FrameDecodeStatus.UNSUPPORTED_PIXEL_FORMAT, width, height, metadata)
    expected_channels = 3
    if pixels.ndim != 3 or pixels.shape[2] != expected_channels or width < 1 or height < 1:
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    if pixels.shape[:2] != (height, width) or not np.issubdtype(pixels.dtype, np.number):
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    if not np.isfinite(pixels).all():
        return _failed(frame, FrameDecodeStatus.CORRUPTED, width, height, metadata)
    try:
        requested_is_finite = frame.requested_timestamp is None or math.isfinite(
            frame.requested_timestamp
        )
        actual_is_finite = actual_timestamp is not None and math.isfinite(actual_timestamp)
        time_base_is_positive = frame.time_base is None or frame.time_base > 0
    except (TypeError, ValueError, OverflowError):
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    if not requested_is_finite:
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    if not actual_is_finite:
        return _failed(frame, FrameDecodeStatus.TIMESTAMP_UNRESOLVED, width, height, metadata)
    if not time_base_is_positive:
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)

    try:
        bit_depth = int((frame.stream_metadata or {}).get("bits_per_component", 8))
        rgb = _to_rgb(pixels, frame.pixel_format, bit_depth)
    except (TypeError, ValueError):
        return _failed(frame, FrameDecodeStatus.INVALID_FRAME, width, height, metadata)
    try:
        rgb = _normalize_range(rgb, frame.color_range, bit_depth)
        linear = _to_linear(rgb, frame.transfer_function, frame.stream_metadata or {})
        xyz = linear @ _RGB_TO_XYZ[_normalize_primaries(frame.color_primaries)].T
        linear_srgb = xyz @ _XYZ_TO_SRGB.T
    except (KeyError, TypeError, ValueError):
        return _failed(frame, FrameDecodeStatus.UNSUPPORTED_COLOR_METADATA, width, height, metadata)

    if _transfer_name(frame.transfer_function) in {"pq", "smpte2084", "hlg", "aribstdb67"}:
        linear_srgb = _tone_map(linear_srgb)
    linear_srgb = np.clip(linear_srgb, 0.0, 1.0).astype(np.float32, copy=False)
    luminance = np.clip(linear_srgb @ _SRGB_LUMA, 0.0, 1.0).astype(np.float32, copy=False)
    linear_srgb.setflags(write=False)
    luminance.setflags(write=False)
    return FrameAnalysisInput(
        width,
        height,
        frame.pixel_format,
        frame.color_primaries,
        frame.transfer_function,
        frame.color_range,
        frame.matrix_coefficients,
        CANONICAL_COLORSPACE,
        (0.0, 1.0),
        linear_srgb,
        luminance,
        None,
        frame.requested_timestamp,
        actual_timestamp,
        frame.pts,
        frame.time_base,
        FrameDecodeStatus.OK,
        metadata,
        frame.error,
    )


# {
#   責務: [normalize_frame_sequence: decoded temporal samplesを正規化しactive-picture rectを共通付与する]
#   処理: [1: 各frameを個別に正規化する 2: temporal barsを保守検出する 3: valid framesへrect metadataを付ける]
#   引数: [frames: 同一videoから時系列に取得したdecoded frames, user_override: optional explicit active rect, consistency: vote比率]
#   戻り値: [analysis_frames: rect metadataを共有するimmutable normalized frame列]
# }
def normalize_frame_sequence(
    frames: Sequence[DecodedVideoFrame],
    *,
    user_override: ActivePictureRect | None = None,
    consistency: float = 0.8,
) -> tuple[FrameAnalysisInput, ...]:
    normalized = tuple(normalize_decoded_frame(frame) for frame in frames)
    rect = detect_active_picture(
        normalized,
        user_override=user_override,
        consistency=consistency,
    )
    if rect is None and normalized:
        first_valid = next((frame for frame in normalized if frame.has_pixels), None)
        if first_valid is not None:
            rect = ActivePictureRect(0, 0, first_valid.width, first_valid.height)
    return tuple(
        replace(frame, active_picture_rect=rect if frame.has_pixels else None)
        for frame in normalized
    )


# {
#   責務: [detect_active_picture: 複数時点で安定した黒帯/pillarboxだけをactive rectから除く]
#   処理: [1: user overrideを優先する 2: frame毎にdark edge候補を抽出する 3: temporal voteと最小領域を確認する]
#   引数: [frames: normalized frames, user_override: optional explicit active rectangle, consistency: temporal vote比率]
#   戻り値: [rect: 安定したactive picture rectangle。判断不能ならNone]
# }
def detect_active_picture(
    frames: Sequence[FrameAnalysisInput],
    *,
    user_override: ActivePictureRect | None = None,
    consistency: float = 0.8,
) -> ActivePictureRect | None:
    if not 0 < consistency <= 1:
        raise ValueError("consistency must be in (0, 1]")
    if not frames:
        return None
    valid_frames = tuple(
        frame
        for frame in frames
        if frame.has_pixels and frame.decode_status is FrameDecodeStatus.OK
    )
    if not valid_frames:
        return None
    width, height = valid_frames[0].width, valid_frames[0].height
    if any(frame.width != width or frame.height != height for frame in valid_frames):
        if user_override is not None:
            raise ValueError("user override requires consistent frame geometry")
        return None
    if user_override is not None:
        if (
            user_override.x < 0
            or user_override.y < 0
            or user_override.width < 1
            or user_override.height < 1
            or user_override.x + user_override.width > width
            or user_override.y + user_override.height > height
        ):
            raise ValueError("active picture override is outside the frame")
        return user_override
    if len(valid_frames) < 2:
        return None
    candidates = [candidate for frame in valid_frames if (candidate := _edge_candidate(frame))]
    if not candidates:
        return None
    rect, count = Counter(candidates).most_common(1)[0]
    if count / len(valid_frames) < consistency:
        return None
    if rect.width < width * _MIN_ACTIVE_FRACTION or rect.height < height * _MIN_ACTIVE_FRACTION:
        return None
    if rect.width == width and rect.height == height:
        return None
    return rect


# {
#   責務: [_edge_candidate: 一つのluminance frameから暗い外周の保守的候補を作る]
#   処理: [1: overall-dark frameを除外する 2: ほぼ全pixelが暗いedgeを走査する 3: contentを残せる候補だけ返す]
#   引数: [frame: normalized frame]
#   戻り値: [candidate: active rect候補またはNone]
# }
def _edge_candidate(frame: FrameAnalysisInput) -> ActivePictureRect | None:
    luminance = frame.luminance
    if luminance is None or frame.decode_status is not FrameDecodeStatus.OK:
        return None
    if float(np.mean(luminance)) <= _DARK_THRESHOLD:
        return None
    height, width = luminance.shape
    row_dark = np.mean(luminance <= _DARK_THRESHOLD, axis=1) >= _EDGE_DARK_RATIO
    column_dark = np.mean(luminance <= _DARK_THRESHOLD, axis=0) >= _EDGE_DARK_RATIO
    top = _leading_band(row_dark)
    bottom = _leading_band(row_dark[::-1])
    left = _leading_band(column_dark)
    right = _leading_band(column_dark[::-1])
    if max(top, bottom, left, right) < _MIN_BAND_PIXELS:
        return None
    if (
        (top and top < height * _MIN_BAND_FRACTION)
        or (bottom and bottom < height * _MIN_BAND_FRACTION)
        or (left and left < width * _MIN_BAND_FRACTION)
        or (right and right < width * _MIN_BAND_FRACTION)
    ):
        return None
    active_width, active_height = width - left - right, height - top - bottom
    if active_width < width * _MIN_ACTIVE_FRACTION or active_height < height * _MIN_ACTIVE_FRACTION:
        return None
    return ActivePictureRect(left, top, active_width, active_height)


# {
#   責務: [_leading_band: frame edgeから続くtrue prefix長を数える]
#   処理: [1: false位置を検索する 2: edgeからの暗帯pixel数を返す]
#   引数: [mask: 1D edge darkness mask]
#   戻り値: [length: leading contiguous true count]
# }
def _leading_band(mask: np.ndarray) -> int:
    indices = np.flatnonzero(~mask)
    return int(indices[0]) if indices.size else int(mask.size)


# {
#   責務: [_failed: error statusをpixelsの無いFrameAnalysisInputへ変換する]
#   処理: [1: geometryを安全化する 2: decode error/status/timingを保持する]
#   引数: [frame: 元decoder result, status: failure state, width/height: geometry, metadata: stream metadata, error: detail]
#   戻り値: [invalid: explicit failure contract]
# }
def _failed(frame, status, width, height, metadata, error=""):
    return FrameAnalysisInput(
        max(0, int(width)),
        max(0, int(height)),
        frame.pixel_format,
        frame.color_primaries,
        frame.transfer_function,
        frame.color_range,
        frame.matrix_coefficients,
        CANONICAL_COLORSPACE,
        (0.0, 1.0),
        None,
        None,
        None,
        frame.requested_timestamp,
        frame.actual_timestamp,
        frame.pts,
        frame.time_base,
        status,
        metadata,
        error or frame.error or status.value,
    )


# {
#   責務: [_to_rgb: supported packed RGB/BGR decoder formatsをRGB float planeにする]
#   処理: [1: integer/float pixel rangeを検証する 2: packed RGB/BGR channel orderを合わせる]
#   引数: [pixels: packed decoded pixels, pixel_format: decoder pixel format]
#   戻り値: [rgb: float32 RGB values in encoded 0..1 domain]
# }
def _to_rgb(pixels: np.ndarray, pixel_format: str, bit_depth: int) -> np.ndarray:
    values = pixels.astype(np.float32, copy=False)
    maximum = float(np.max(values)) if values.size else 0.0
    if np.issubdtype(pixels.dtype, np.integer):
        storage_bits = 8 if pixel_format.casefold().endswith("24") else 16
        if np.iinfo(pixels.dtype).bits != storage_bits:
            raise ValueError("pixel storage does not match pixel format")
        if not 8 <= bit_depth <= np.iinfo(pixels.dtype).bits:
            raise ValueError("unsupported pixel bit depth")
        maximum_value = float((1 << bit_depth) - 1)
        if maximum > maximum_value or float(np.min(values)) < 0:
            raise ValueError("pixel values exceed declared bit depth")
        values = values / maximum_value
    elif maximum > 1.0 or float(np.min(values)) < 0.0:
        raise ValueError("floating pixel values must be in 0..1")
    format_name = pixel_format.casefold()
    if format_name.startswith("bgr"):
        values = values[:, :, [2, 1, 0]]
    else:
        values = values[:, :, :3]
    return np.clip(values, 0.0, 1.0)


# {
#   責務: [_normalize_range: limited/full RGB code valuesを0..1へ正規化する]
#   処理: [1: range descriptorを検証する 2: limited rangeは16..235相当を展開する]
#   引数: [rgb: encoded RGB float values, color_range: full/limited]
#   戻り値: [normalized: expanded RGB values]
# }
def _normalize_range(rgb, color_range, bit_depth):
    normalized_range = color_range.casefold()
    if normalized_range == "full":
        return rgb
    if normalized_range == "limited":
        scale = float(1 << (bit_depth - 8))
        maximum = float((1 << bit_depth) - 1)
        low = (16.0 * scale) / maximum
        width = (219.0 * scale) / maximum
        return np.clip((rgb - low) / width, 0.0, 1.0)
    raise ValueError("unsupported color range")


# {
#   責務: [_normalize_primaries: supported source primariesを変換行列keyへ正規化する]
#   処理: [1: case/aliasを正規化する 2: 未対応primariesを拒否する]
#   引数: [primaries: decoder color primaries tag]
#   戻り値: [matrix key: BT.709、BT.2020またはDisplay P3]
# }
def _normalize_primaries(primaries):
    normalized = primaries.casefold().replace(" ", "")
    aliases = {
        "bt.709": "bt709",
        "bt709": "bt709",
        "bt.2020": "bt2020",
        "bt2020": "bt2020",
        "smpte432": "display-p3",
        "displayp3": "display-p3",
        "p3d65": "display-p3",
    }
    result = aliases.get(normalized)
    if result is None:
        raise ValueError("unsupported color primaries")
    return result


# {
#   責務: [_transfer_name: transfer-function aliasを共通keyへ正規化する]
#   処理: [1: caseを統一する 2: separatorを除去してalias比較可能なnameを返す]
#   引数: [transfer: decoder transfer tag]
#   戻り値: [name: normalized transfer key]
# }
def _transfer_name(transfer: str) -> str:
    return transfer.casefold().replace("-", "").replace("_", "")


# {
#   責務: [_to_linear: SDR/PQ/HLG transfer functionをrelative linear lightへ復号する]
#   処理: [1: transfer aliasを正規化する 2: EOTFを適用しHDRはpeak nits情報を使う]
#   引数: [encoded: normalized encoded RGB values, transfer: transfer tag, metadata: stream mastering metadata]
#   戻り値: [linear: relative linear RGB values]
# }
def _to_linear(encoded, transfer, metadata):
    name = _transfer_name(transfer)
    encoded = np.clip(encoded, 0.0, 1.0)
    if name in {"srgb", "iec6196621"}:
        return np.where(encoded <= 0.04045, encoded / 12.92, ((encoded + 0.055) / 1.055) ** 2.4)
    if name in {"bt709", "bt.709", "bt1886", "gamma22"}:
        return np.where(encoded < 0.081, encoded / 4.5, ((encoded + 0.099) / 1.099) ** (1.0 / 0.45))
    if name in {"pq", "smpte2084"}:
        m1, m2 = 2610 / 16384, 2523 / 32
        c1, c2, c3 = 3424 / 4096, 2413 / 128, 2392 / 128
        power = encoded ** (1 / m2)
        luminance = (np.maximum(power - c1, 0) / np.maximum(c2 - c3 * power, 1e-8)) ** (1 / m1)
        return luminance * (10000.0 / 203.0)
    if name in {"hlg", "aribstdb67"}:
        a, b, c = 0.17883277, 0.28466892, 0.55991073
        scene_linear = np.where(
            encoded <= 0.5, encoded**2 / 3.0, (np.exp((encoded - c) / a) + b) / 12.0
        )
        gamma = float(metadata.get("hlg_system_gamma", 1.2))
        peak_nits = float(metadata.get("max_luminance_nits", 1000.0))
        if not math.isfinite(gamma) or gamma <= 0 or not math.isfinite(peak_nits) or peak_nits <= 0:
            raise ValueError("invalid HLG mastering metadata")
        return scene_linear**gamma * (peak_nits / 203.0)
    raise ValueError("unsupported transfer function")


# {
#   責務: [_tone_map: HDR relative linear RGBを解析向けSDR linear rangeへ圧縮する]
#   処理: [1: scene luminanceを求める 2: Reinhard圧縮を適用する 3: RGB hue比を維持する]
#   引数: [linear_rgb: source-primary relative linear RGB]
#   戻り値: [mapped: bounded linear RGB]
# }
def _tone_map(linear_rgb):
    luminance = np.maximum(linear_rgb @ _SRGB_LUMA, 0.0)
    mapped_luminance = luminance / (1.0 + luminance)
    scale = np.divide(
        mapped_luminance, luminance, out=np.zeros_like(luminance), where=luminance > 1e-8
    )
    return linear_rgb * scale[:, :, None]
