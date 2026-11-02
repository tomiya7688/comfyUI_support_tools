"""Minimal validated VMD 0002 bone-key serializer."""

from __future__ import annotations

import math
import struct

from .contracts import VmdBoneKey

VMD_HEADER = b"Vocaloid Motion Data 0002"
BONE_INTERPOLATION = bytes((20, 20, 107, 107)) * 16
MAX_RECORDS = 5_000_000


# {
# 責務: [write_motion_vmd: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def write_motion_vmd(keys: tuple[VmdBoneKey, ...], model_name: str = "") -> bytes:
    ordered = sorted(keys, key=lambda key: (key.frame, key.bone.casefold()))
    if len(ordered) > MAX_RECORDS:
        raise ValueError("motion VMD exceeds the maximum bone key count")
    records = bytearray()
    for key in ordered:
        name = key.bone.encode("shift_jis", errors="strict")
        if (
            not name
            or len(name) > 15
            or len(key.translation) != 3
            or len(key.rotation) != 4
            or not isinstance(key.frame, int)
            or isinstance(key.frame, bool)
            or key.frame < 0
            or key.frame > 0xFFFFFFFF
            or any(not math.isfinite(value) for value in (*key.translation, *key.rotation))
        ):
            raise ValueError(f"invalid VMD bone key {key.bone!r} at frame {key.frame}")
        rotation = _normalize_quaternion(key.rotation)
        records.extend(name.ljust(15, b"\0"))
        records.extend(struct.pack("<I3f4f", key.frame, *key.translation, *rotation))
        records.extend(BONE_INTERPOLATION)
    header = VMD_HEADER.ljust(30, b"\0")
    encoded_model = _encode_fixed_name(model_name, 20)
    output = bytearray(header + encoded_model)
    output.extend(struct.pack("<I", len(ordered)))
    output.extend(records)
    # Morph, camera, light, shadow, model-display, and IK-display sections.
    output.extend(struct.pack("<I", 0))
    output.extend(struct.pack("<I", 0))
    output.extend(struct.pack("<I", 0))
    output.extend(struct.pack("<I", 0))
    output.extend(struct.pack("<I", 0))
    output.extend(struct.pack("<I", 0))
    return bytes(output)


# {
# 責務: [_encode_fixed_name: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _encode_fixed_name(name: str, width: int) -> bytes:
    """Encode a VMD fixed-width Shift-JIS name without silent data loss."""
    encoded = name.encode("shift_jis", errors="strict")
    if len(encoded) > width:
        raise ValueError(f"VMD name must fit within {width} Shift-JIS bytes")
    return encoded.ljust(width, b"\0")


# {
# 責務: [_normalize_quaternion: function responsibility for the motion recovery pipeline]
# 処理: [validate input and perform the requested conversion step]
# 引数: [typed request values: processing inputs]
# 戻り値: [typed result: processed motion output]
# }
def _normalize_quaternion(
    rotation: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if len(rotation) != 4 or any(not math.isfinite(value) for value in rotation):
        raise ValueError("VMD quaternion must contain four finite values")
    magnitude = math.hypot(*rotation)
    if not math.isfinite(magnitude):
        raise ValueError("VMD quaternion magnitude must be finite")
    if magnitude < 1e-8:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(value / magnitude for value in rotation)
