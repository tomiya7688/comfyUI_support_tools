"""Bounded VMD reader and camera-only writer."""

from __future__ import annotations

import math
import struct
from pathlib import Path

from .contracts import CameraKey, DanceMotion, MotionKey

VMD_HEADER = b"Vocaloid Motion Data 0002"
MAX_VMD_BYTES = 512 * 1024 * 1024
MAX_RECORDS = 5_000_000


# {
# 責務: [VmdFormatError: VMD入力の形式エラーを表す]
# フィールド: [ValueError]
# 処理: [不正・切り詰めたbinaryを区別して通知する]
# }
class VmdFormatError(ValueError):
    pass


# {
# 責務: [_Reader: VMD binaryのbounds checked reader]
# フィールド: [data, offset]
# 処理: [record count/byte boundaryを安全に読む]
# }
class _Reader:
    # {
    # 責務: [__init__: reader stateを初期化する]
    # 処理: [binaryとoffsetを保持する]
    # 引数: [data: VMD file bytes]
    # 戻り値: [None: なし]
    # }
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    # {
    # 責務: [take: 指定長binaryを境界内から読む]
    # 処理: [sizeを検証してoffsetを進める]
    # 引数: [size: byte count]
    # 戻り値: [bytes: 読み込んだ範囲]
    # }
    def take(self, size: int) -> bytes:
        if size < 0 or self.offset + size > len(self.data):
            raise VmdFormatError(f"truncated VMD at byte {self.offset}")
        start = self.offset
        self.offset += size
        return self.data[start : self.offset]

    # {
    # 責務: [unpack: struct値をlittle endianで読む]
    # 処理: [format長を読み境界検査する]
    # 引数: [format_code: struct format]
    # 戻り値: [tuple: unpacked values]
    # }
    def unpack(self, format_code: str) -> tuple:
        return struct.unpack(format_code, self.take(struct.calcsize(format_code)))

    # {
    # 責務: [count: record countを制限内で読む]
    # 処理: [unsigned countを検証して返す]
    # 引数: [label: section名]
    # 戻り値: [int: record数]
    # }
    def count(self, label: str) -> int:
        value = self.unpack("<I")[0]
        if value > MAX_RECORDS:
            raise VmdFormatError(f"{label} count exceeds limit: {value}")
        return value


# {
# 責務: [read_dance_vmd: VMDからbone位置trackを読む]
# 処理: [1: header/bone keyを検証, 2: frame durationとroot motionを返す]
# 引数: [path: VMD path, fps: playback fps]
# 戻り値: [DanceMotion: 抽出したmotion]
# }
def read_dance_vmd(path: str | Path, fps: int = 30) -> DanceMotion:
    if not isinstance(fps, int) or isinstance(fps, bool) or fps <= 0:
        raise ValueError("fps must be a positive integer")
    source = Path(path)
    size = source.stat().st_size
    if size <= 0 or size > MAX_VMD_BYTES:
        raise VmdFormatError(f"VMD size must be between 1 and {MAX_VMD_BYTES}")
    with source.open("rb") as stream:
        data = stream.read(MAX_VMD_BYTES + 1)
    if len(data) <= 0 or len(data) > MAX_VMD_BYTES:
        raise VmdFormatError(f"VMD size must be between 1 and {MAX_VMD_BYTES}")
    reader = _Reader(data)
    header = reader.take(30)
    if not header.startswith(VMD_HEADER):
        raise VmdFormatError("unsupported VMD header")
    reader.take(20)  # model name
    keys = []
    for _ in range(reader.count("bone")):
        raw_name = reader.take(15).split(b"\0", 1)[0]
        try:
            name = raw_name.decode("shift_jis", errors="strict")
        except UnicodeDecodeError as error:
            raise VmdFormatError("invalid shift-jis bone name") from error
        frame = reader.unpack("<I")[0]
        values = reader.unpack("<7f")
        if any(not math.isfinite(value) for value in values):
            raise VmdFormatError(f"non-finite bone key at frame {frame}")
        keys.append(MotionKey(name, frame, tuple(values[:3])))
        reader.take(64)  # bone interpolation
    morph_count = reader.count("morph")
    reader.take(morph_count * 23)
    camera_count = reader.count("camera")
    reader.take(camera_count * 61)
    light_count = reader.count("light")
    reader.take(light_count * 28)
    shadow_count = reader.count("self shadow")
    reader.take(shadow_count * 9)
    if reader.offset < len(reader.data):
        display_count = reader.count("model display")
        for _ in range(display_count):
            reader.take(5)  # frame and show flag
            ik_count = reader.count("IK toggle")
            reader.take(ik_count * 21)
    if reader.offset != len(reader.data):
        raise VmdFormatError("unexpected trailing bytes after VMD sections")
    if fps <= 0:
        raise ValueError("fps must be positive")
    duration = max((key.frame for key in keys), default=0)
    return DanceMotion(source, tuple(keys), duration, fps)


# {
# 責務: [write_camera_vmd: camera planをVMD 0002へserializeする]
# 処理: [section countを構成しcamera keyをbinary exportする]
# 引数: [keys: camera keyframes, model_name: header name]
# 戻り値: [bytes: camera VMD data]
# }
def write_camera_vmd(keys: tuple[CameraKey, ...], model_name: str = "") -> bytes:
    if not keys:
        raise ValueError("camera VMD requires at least one keyframe")
    ordered = tuple(sorted(keys, key=lambda key: key.frame))
    if len({key.frame for key in ordered}) != len(ordered):
        raise ValueError("camera keyframes must have unique frame numbers")
    output = bytearray(VMD_HEADER.ljust(30, b"\0"))
    encoded_name = model_name.encode("shift_jis", errors="strict")
    if len(encoded_name) > 20:
        raise ValueError("VMD model name must fit within 20 Shift-JIS bytes")
    output.extend(encoded_name.ljust(20, b"\0"))
    output.extend(struct.pack("<I", 0))  # bone keys
    output.extend(struct.pack("<I", 0))  # morph keys
    output.extend(struct.pack("<I", len(ordered)))
    interpolation = bytes((20, 20, 107, 107)) * 6
    for key in ordered:
        numeric = (key.distance, *key.position, *key.rotation)
        if (
            not isinstance(key.frame, int)
            or isinstance(key.frame, bool)
            or key.frame < 0
            or key.frame > 0xFFFFFFFF
            or any(not math.isfinite(value) for value in numeric)
        ):
            raise ValueError(f"invalid camera key at frame {key.frame}")
        if (
            key.distance < 0
            or not isinstance(key.field_of_view, int)
            or isinstance(key.field_of_view, bool)
            or not 1 <= key.field_of_view <= 180
        ):
            raise ValueError(f"invalid camera distance or field of view at frame {key.frame}")
        output.extend(struct.pack("<If3f3f", key.frame, key.distance, *key.position, *key.rotation))
        output.extend(interpolation)
        output.extend(struct.pack("<IB", key.field_of_view, int(not key.perspective)))
    output.extend(struct.pack("<I", 0))  # light keys
    output.extend(struct.pack("<I", 0))  # shadow keys
    output.extend(struct.pack("<I", 0))  # model display / IK frames
    return bytes(output)
