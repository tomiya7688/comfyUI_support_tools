"""Bounded reader for PMX 2.0/2.1 structures used by the Model Doctor."""

from __future__ import annotations

import math
import struct
from pathlib import Path

from .contracts import (
    DiagnosticSeverity,
    PmxBone,
    PmxDiagnostic,
    PmxJoint,
    PmxModel,
    PmxRigidBody,
    PmxVertex,
)

MAX_PMX_BYTES = 512 * 1024 * 1024
MAX_RECORDS = 5_000_000


# {
# 責務: [PmxFormatError: PMX doctorの型または処理単位を表す]
# フィールド: [型と診断に必要な状態]
# 処理: [安全なPMX診断・候補生成を支援する]
# }
class PmxFormatError(ValueError):
    """PMX bytes are truncated, malformed, or exceed parser safety limits."""


# {
# 責務: [_Reader: PMX doctorの型または処理単位を表す]
# フィールド: [型と診断に必要な状態]
# 処理: [安全なPMX診断・候補生成を支援する]
# }
class _Reader:
    # {
    # 責務: [__init__: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [data: 呼び出しに必要な値]
    # 戻り値: [None: 処理結果]
    # }
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    # {
    # 責務: [take: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [size: 呼び出しに必要な値]
    # 戻り値: [bytes: 処理結果]
    # }
    def take(self, size: int) -> bytes:
        if size < 0 or size > MAX_PMX_BYTES or self.offset + size > len(self.data):
            raise PmxFormatError(f"truncated PMX at byte {self.offset} while reading {size} bytes")
        start = self.offset
        self.offset += size
        return self.data[start : self.offset]

    # {
    # 責務: [unpack: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [format_code: 呼び出しに必要な値]
    # 戻り値: [tuple: 処理結果]
    # }
    def unpack(self, format_code: str) -> tuple:
        size = struct.calcsize(format_code)
        return struct.unpack(format_code, self.take(size))

    # {
    # 責務: [u8: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [なし: 呼び出しに必要な値]
    # 戻り値: [int: 処理結果]
    # }
    def u8(self) -> int:
        return self.unpack("<B")[0]

    # {
    # 責務: [u16: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [なし: 呼び出しに必要な値]
    # 戻り値: [int: 処理結果]
    # }
    def u16(self) -> int:
        return self.unpack("<H")[0]

    # {
    # 責務: [i32: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [なし: 呼び出しに必要な値]
    # 戻り値: [int: 処理結果]
    # }
    def i32(self) -> int:
        return self.unpack("<i")[0]

    # {
    # 責務: [f32: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [なし: 呼び出しに必要な値]
    # 戻り値: [float: 処理結果]
    # }
    def f32(self) -> float:
        return self.unpack("<f")[0]

    # {
    # 責務: [vec: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [count: 呼び出しに必要な値]
    # 戻り値: [tuple[float, ...]: 処理結果]
    # }
    def vec(self, count: int) -> tuple[float, ...]:
        return self.unpack("<" + "f" * count)

    # {
    # 責務: [index: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [size, signed: 呼び出しに必要な値]
    # 戻り値: [int: 処理結果]
    # }
    def index(self, size: int, signed: bool = True) -> int:
        formats = {
            (1, True): "<b",
            (1, False): "<B",
            (2, True): "<h",
            (2, False): "<H",
            (4, True): "<i",
            (4, False): "<I",
        }
        try:
            return self.unpack(formats[(size, signed)])[0]
        except KeyError as error:
            raise PmxFormatError(f"unsupported PMX index size: {size}") from error

    # {
    # 責務: [count: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [label: 呼び出しに必要な値]
    # 戻り値: [int: 処理結果]
    # }
    def count(self, label: str) -> int:
        value = self.i32()
        if value < 0 or value > MAX_RECORDS:
            raise PmxFormatError(f"invalid {label} count {value} at byte {self.offset - 4}")
        return value

    # {
    # 責務: [text: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [encoding: 呼び出しに必要な値]
    # 戻り値: [str: 処理結果]
    # }
    def text(self, encoding: str) -> str:
        length = self.i32()
        if length < 0 or length > 16 * 1024 * 1024:
            raise PmxFormatError(f"invalid string length {length} at byte {self.offset - 4}")
        try:
            return self.take(length).decode(encoding, errors="strict")
        except UnicodeDecodeError as error:
            raise PmxFormatError(
                f"invalid {encoding} string at byte {self.offset - length}"
            ) from error

    # {
    # 責務: [skip_text: PMX doctorの関連処理を実行する]
    # 処理: [入力を検証し、安全な結果を返す]
    # 引数: [encoding: 呼び出しに必要な値]
    # 戻り値: [None: 処理結果]
    # }
    def skip_text(self, encoding: str) -> None:
        self.text(encoding)


# {
# 責務: [parse_pmx: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [path: 呼び出しに必要な値]
# 戻り値: [PmxModel: 処理結果]
# }
def parse_pmx(path: str | Path) -> PmxModel:
    """Parse PMX 2.0/2.1 with strict lengths and retain only repairable values."""
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as error:
        raise PmxFormatError(f"cannot read PMX file: {error}") from error
    if size <= 0 or size > MAX_PMX_BYTES:
        raise PmxFormatError(f"PMX file size must be between 1 byte and {MAX_PMX_BYTES}")
    return parse_pmx_bytes(source.read_bytes(), source_path=source)


# {
# 責務: [parse_pmx_bytes: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [data, source_path: 呼び出しに必要な値]
# 戻り値: [PmxModel: 処理結果]
# }
def parse_pmx_bytes(data: bytes, source_path: Path | None = None) -> PmxModel:
    reader = _Reader(data)
    diagnostics: list[PmxDiagnostic] = []
    if reader.take(4) != b"PMX ":
        raise PmxFormatError("file does not start with a PMX signature")
    version = reader.f32()
    if not math.isfinite(version) or not 2.0 <= version <= 2.1:
        raise PmxFormatError(f"unsupported PMX version: {version}")
    global_size = reader.u8()
    if global_size != 8:
        raise PmxFormatError(f"invalid PMX global header size: {global_size}")
    globals_data = tuple(reader.take(global_size))
    encoding = "utf-16-le" if globals_data[0] == 0 else "utf-8" if globals_data[0] == 1 else ""
    if not encoding:
        raise PmxFormatError(f"unsupported text encoding id: {globals_data[0]}")
    additional_uv = globals_data[1]
    sizes = globals_data[2:8]
    if additional_uv > 4 or any(value not in (1, 2, 4) for value in sizes):
        raise PmxFormatError("invalid PMX additional UV count or index-size table")
    (
        vertex_index_size,
        texture_index_size,
        material_index_size,
        bone_index_size,
        morph_index_size,
        rigid_index_size,
    ) = sizes
    model_name = reader.text(encoding)
    reader.skip_text(encoding)
    reader.skip_text(encoding)
    reader.skip_text(encoding)

    vertices = _read_vertices(reader, vertex_index_size, bone_index_size, additional_uv)
    face_index_count = reader.count("face index")
    if face_index_count % 3:
        raise PmxFormatError(f"face index count is not divisible by 3: {face_index_count}")
    faces = tuple(
        tuple(reader.index(vertex_index_size, signed=False) for _ in range(3))
        for _ in range(face_index_count // 3)
    )
    for face_index, face in enumerate(faces):
        if any(index >= len(vertices) for index in face):
            diagnostics.append(
                _diagnostic(
                    "mesh.face_vertex_reference",
                    "mesh",
                    f"face:{face_index}",
                    "Face refers to a missing vertex",
                    indices=face,
                )
            )
    texture_count = reader.count("texture")
    for _ in range(texture_count):
        reader.skip_text(encoding)
    material_count = reader.count("material")
    material_names = []
    for material_index in range(material_count):
        name = reader.text(encoding)
        reader.skip_text(encoding)
        material_names.append(name)
        reader.take(16 + 12 + 4 + 12 + 1 + 16 + 4)
        texture_index = reader.index(texture_index_size)
        sphere_index = reader.index(texture_index_size)
        reader.u8()
        shared_toon = reader.u8()
        toon_index = reader.u8() if shared_toon else reader.index(texture_index_size)
        reader.skip_text(encoding)
        reader.i32()
        toon_limit = 10 if shared_toon else texture_count
        if (
            texture_index >= texture_count
            or sphere_index >= texture_count
            or toon_index >= toon_limit
        ):
            diagnostics.append(
                _diagnostic(
                    "material.texture_reference",
                    "material",
                    f"material:{material_index}:{name}",
                    "Material references an out-of-range texture",
                    texture=texture_index,
                    sphere=sphere_index,
                    toon=toon_index,
                )
            )

    bones = _read_bones(reader, encoding, bone_index_size)
    morph_count, morph_diagnostics, morph_rigid_refs = _read_morphs(
        reader,
        encoding,
        vertex_index_size,
        material_index_size,
        bone_index_size,
        morph_index_size,
        rigid_index_size,
        len(vertices),
        material_count,
        len(bones),
    )
    diagnostics.extend(morph_diagnostics)
    diagnostics.extend(
        _read_display_frames(
            reader, encoding, bone_index_size, morph_index_size, len(bones), morph_count
        )
    )
    rigid_bodies = _read_rigid_bodies(reader, encoding, bone_index_size)
    for target, rigid_index in morph_rigid_refs:
        if not 0 <= rigid_index < len(rigid_bodies):
            diagnostics.append(
                _diagnostic(
                    "morph.reference",
                    "morph",
                    target,
                    "Impulse morph references a missing rigid body",
                    index=rigid_index,
                )
            )
    joints = _read_joints(reader, encoding, rigid_index_size)
    if version >= 2.1:
        soft_count = reader.count("soft body")
        if soft_count:
            raise PmxFormatError(
                "PMX 2.1 soft-body records are not yet supported; refusing a partial physics audit"
            )
    if reader.offset != len(data):
        diagnostics.append(
            _diagnostic(
                "pmx.trailing_data",
                "format",
                "file",
                "PMX contains bytes after the parsed model sections",
                trailing=len(data) - reader.offset,
            )
        )
    diagnostics.extend(_validate_bones(bones))
    diagnostics.extend(_validate_rigid_physics(rigid_bodies, joints, len(bones)))
    return PmxModel(
        source_path=source_path,
        source_bytes=data,
        version=version,
        model_name=model_name,
        vertices=vertices,
        faces=faces,
        bones=bones,
        morph_count=morph_count,
        material_count=material_count,
        rigid_bodies=rigid_bodies,
        joints=joints,
        diagnostics=tuple(diagnostics),
        bone_index_size=bone_index_size,
    )


# {
# 責務: [_read_vertices: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [reader, vertex_index_size, bone_index_size, additional_uv: 呼び出しに必要な値]
# 戻り値: [tuple[PmxVertex, ...]: 処理結果]
# }
def _read_vertices(
    reader: _Reader, vertex_index_size: int, bone_index_size: int, additional_uv: int
) -> tuple[PmxVertex, ...]:
    count = reader.count("vertex")
    result = []
    for index in range(count):
        position = reader.vec(3)
        reader.take(12 + 8 + additional_uv * 16)
        weight_type = reader.u8()
        bone_offsets: list[int] = []
        weights: tuple[float, ...]
        weight_offsets: list[int] = []
        if weight_type == 0:
            bone_offsets.append(reader.offset)
            bones = (reader.index(bone_index_size),)
            weights = (1.0,)
        elif weight_type in (1, 3):
            bone_offsets.extend((reader.offset, reader.offset + bone_index_size))
            bones = (reader.index(bone_index_size), reader.index(bone_index_size))
            weight_offsets.append(reader.offset)
            weights = (reader.f32(),)
            if weight_type == 3:
                reader.take(36)
        elif weight_type in (2, 4):
            bone_offsets.extend(reader.offset + item * bone_index_size for item in range(4))
            bones = tuple(reader.index(bone_index_size) for _ in range(4))
            weight_offsets.extend(reader.offset + item * 4 for item in range(4))
            weights = tuple(reader.unpack("<4f"))
        else:
            raise PmxFormatError(f"unknown vertex weight type {weight_type} at vertex {index}")
        reader.f32()
        result.append(
            PmxVertex(
                index,
                position,
                weight_type,
                bones,
                weights,
                tuple(bone_offsets),
                tuple(weight_offsets),
            )
        )
    return tuple(result)


# {
# 責務: [_read_bones: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [reader, encoding, bone_index_size: 呼び出しに必要な値]
# 戻り値: [tuple[PmxBone, ...]: 処理結果]
# }
def _read_bones(reader: _Reader, encoding: str, bone_index_size: int) -> tuple[PmxBone, ...]:
    result = []
    for index in range(reader.count("bone")):
        name = reader.text(encoding)
        reader.skip_text(encoding)
        reader.take(12)
        parent_offset = reader.offset
        parent = reader.index(bone_index_size)
        reader.i32()
        flags = reader.u16()
        if flags & 0x0001:
            reader.index(bone_index_size)
        else:
            reader.take(12)
        if flags & (0x0100 | 0x0200):
            reader.index(bone_index_size)
            reader.f32()
        if flags & 0x0400:
            reader.take(12)
        if flags & 0x0800:
            reader.take(24)
        if flags & 0x2000:
            reader.i32()
        ik_target = None
        links: list[int] = []
        if flags & 0x0020:
            ik_target = reader.index(bone_index_size)
            reader.i32()
            reader.f32()
            for _ in range(reader.count("IK link")):
                links.append(reader.index(bone_index_size))
                if reader.u8():
                    reader.take(24)
        result.append(PmxBone(index, name, parent, flags, parent_offset, ik_target, tuple(links)))
    return tuple(result)


# {
# 責務: [_read_morphs: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [reader, encoding, vertex_size, material_size, bone_size, morph_size, rigid_size, vertex_count, material_count, bone_count: 呼び出しに必要な値]
# 戻り値: [処理結果: 処理結果]
# }
def _read_morphs(
    reader,
    encoding,
    vertex_size,
    material_size,
    bone_size,
    morph_size,
    rigid_size,
    vertex_count,
    material_count,
    bone_count,
):
    diagnostics = []
    rigid_references = []
    count = reader.count("morph")
    for morph_index in range(count):
        name = reader.text(encoding)
        reader.skip_text(encoding)
        reader.u8()
        morph_type = reader.u8()
        for offset_index in range(reader.count("morph offset")):
            target = f"morph:{morph_index}:{name}:offset:{offset_index}"
            if morph_type == 0:
                target_index = reader.index(morph_size)
                reader.f32()
                if not 0 <= target_index < count:
                    diagnostics.append(
                        _diagnostic(
                            "morph.reference",
                            "morph",
                            target,
                            "Group morph references a missing morph",
                            index=target_index,
                        )
                    )
            elif morph_type == 1:
                target_index = reader.index(vertex_size, signed=False)
                reader.take(12)
                if target_index >= vertex_count:
                    diagnostics.append(
                        _diagnostic(
                            "morph.reference",
                            "morph",
                            target,
                            "Vertex morph references a missing vertex",
                            index=target_index,
                        )
                    )
            elif morph_type == 2:
                target_index = reader.index(bone_size)
                reader.take(28)
                if not 0 <= target_index < bone_count:
                    diagnostics.append(
                        _diagnostic(
                            "morph.reference",
                            "morph",
                            target,
                            "Bone morph references a missing bone",
                            index=target_index,
                        )
                    )
            elif 3 <= morph_type <= 7:
                target_index = reader.index(vertex_size, signed=False)
                reader.take(16)
                if target_index >= vertex_count:
                    diagnostics.append(
                        _diagnostic(
                            "morph.reference",
                            "morph",
                            target,
                            "UV morph references a missing vertex",
                            index=target_index,
                        )
                    )
            elif morph_type == 8:
                target_index = reader.index(material_size)
                reader.u8()
                reader.take(112)
                if target_index != -1 and not 0 <= target_index < material_count:
                    diagnostics.append(
                        _diagnostic(
                            "morph.reference",
                            "morph",
                            target,
                            "Material morph references a missing material",
                            index=target_index,
                        )
                    )
            elif morph_type == 9:
                target_index = reader.index(morph_size)
                reader.f32()
                if target_index >= count:
                    diagnostics.append(
                        _diagnostic(
                            "morph.reference",
                            "morph",
                            target,
                            "Flip morph references a missing morph",
                            index=target_index,
                        )
                    )
            elif morph_type == 10:
                target_index = reader.index(rigid_size)
                reader.u8()
                reader.take(24)
                rigid_references.append((target, target_index))
            else:
                raise PmxFormatError(f"unknown morph type {morph_type} in {target}")
    return count, diagnostics, rigid_references


# {
# 責務: [_read_display_frames: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [reader, encoding, bone_size, morph_size, bone_count, morph_count: 呼び出しに必要な値]
# 戻り値: [処理結果: 処理結果]
# }
def _read_display_frames(reader, encoding, bone_size, morph_size, bone_count, morph_count):
    diagnostics = []
    for frame_index in range(reader.count("display frame")):
        name = reader.text(encoding)
        reader.skip_text(encoding)
        reader.u8()
        for element_index in range(reader.count("display element")):
            kind = reader.u8()
            index = reader.index(bone_size if kind == 0 else morph_size)
            limit = bone_count if kind == 0 else morph_count
            if kind not in (0, 1) or not 0 <= index < limit:
                diagnostics.append(
                    _diagnostic(
                        "display.reference",
                        "rig",
                        f"display:{frame_index}:{name}:{element_index}",
                        "Display frame references an invalid bone/morph",
                        index=index,
                    )
                )
    return diagnostics


# {
# 責務: [_read_rigid_bodies: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [reader, encoding, bone_size: 呼び出しに必要な値]
# 戻り値: [処理結果: 処理結果]
# }
def _read_rigid_bodies(reader, encoding, bone_size):
    result = []
    for index in range(reader.count("rigid body")):
        name = reader.text(encoding)
        reader.skip_text(encoding)
        bone = reader.index(bone_size)
        reader.u8()
        reader.u16()
        shape = reader.u8()
        reader.take(36)
        values = []
        for _ in range(5):
            values.append((reader.offset, reader.f32()))
        mode = reader.u8()
        result.append(
            PmxRigidBody(
                index,
                name,
                bone,
                shape,
                mode,
                *(value for _offset, value in values),
                tuple(offset for offset, _value in values),
            )
        )
    return tuple(result)


# {
# 責務: [_read_joints: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [reader, encoding, rigid_size: 呼び出しに必要な値]
# 戻り値: [処理結果: 処理結果]
# }
def _read_joints(reader, encoding, rigid_size):
    result = []
    for index in range(reader.count("joint")):
        name = reader.text(encoding)
        reader.skip_text(encoding)
        kind = reader.u8()
        if kind != 0:
            raise PmxFormatError(f"unsupported PMX joint type {kind} at joint {index}")
        body_a, body_b = reader.index(rigid_size), reader.index(rigid_size)
        reader.take(24)
        min_offsets = []
        minimum = []
        for _ in range(6):
            min_offsets.append(reader.offset)
            minimum.append(reader.f32())
        max_offsets = []
        maximum = []
        for _ in range(6):
            max_offsets.append(reader.offset)
            maximum.append(reader.f32())
        reader.take(24)
        result.append(
            PmxJoint(
                index,
                name,
                body_a,
                body_b,
                tuple(min_offsets),
                tuple(max_offsets),
                tuple(minimum),
                tuple(maximum),
            )
        )
    return tuple(result)


# {
# 責務: [_validate_bones: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [bones: 呼び出しに必要な値]
# 戻り値: [list[PmxDiagnostic]: 処理結果]
# }
def _validate_bones(bones: tuple[PmxBone, ...]) -> list[PmxDiagnostic]:
    diagnostics = []
    seen: dict[str, int] = {}
    for bone in bones:
        if bone.name in seen:
            diagnostics.append(
                _diagnostic(
                    "bone.duplicate_name",
                    "skeleton",
                    f"bone:{bone.index}:{bone.name}",
                    "Bone name is duplicated",
                    other_index=seen[bone.name],
                )
            )
        seen[bone.name] = bone.index
        if (
            bone.parent_index < -1
            or bone.parent_index >= len(bones)
            or bone.parent_index == bone.index
        ):
            diagnostics.append(
                _diagnostic(
                    "bone.invalid_parent",
                    "skeleton",
                    f"bone:{bone.index}:{bone.name}",
                    "Bone parent index is invalid or self-referential",
                    parent=bone.parent_index,
                )
            )
        if bone.ik_target is not None and not 0 <= bone.ik_target < len(bones):
            diagnostics.append(
                _diagnostic(
                    "ik.invalid_target",
                    "ik",
                    f"bone:{bone.index}:{bone.name}",
                    "IK target references a missing bone",
                    target=bone.ik_target,
                )
            )
        for link in bone.ik_links:
            if not 0 <= link < len(bones):
                diagnostics.append(
                    _diagnostic(
                        "ik.invalid_link",
                        "ik",
                        f"bone:{bone.index}:{bone.name}",
                        "IK link references a missing bone",
                        link=link,
                    )
                )
    return diagnostics


# {
# 責務: [_validate_rigid_physics: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [rigid_bodies, joints, bone_count: 呼び出しに必要な値]
# 戻り値: [処理結果: 処理結果]
# }
def _validate_rigid_physics(rigid_bodies, joints, bone_count):
    diagnostics = []
    for body in rigid_bodies:
        if body.bone_index < -1 or body.bone_index >= bone_count:
            diagnostics.append(
                _diagnostic(
                    "physics.invalid_bone",
                    "physics",
                    f"rigid:{body.index}:{body.name}",
                    "Rigid body refers to a missing bone",
                    bone=body.bone_index,
                )
            )
        if body.shape not in (0, 1, 2) or body.mode not in (0, 1, 2):
            diagnostics.append(
                _diagnostic(
                    "physics.invalid_mode",
                    "physics",
                    f"rigid:{body.index}:{body.name}",
                    "Rigid body shape or mode is invalid",
                    shape=body.shape,
                    mode=body.mode,
                )
            )
        if (
            body.mass < 0
            or body.linear_damping < 0
            or body.angular_damping < 0
            or body.restitution < 0
            or body.friction < 0
        ):
            diagnostics.append(
                _diagnostic(
                    "physics.negative_parameter",
                    "physics",
                    f"rigid:{body.index}:{body.name}",
                    "Rigid body has negative mass or damping/material parameter",
                )
            )
        if any(
            not math.isfinite(value)
            for value in (
                body.mass,
                body.linear_damping,
                body.angular_damping,
                body.restitution,
                body.friction,
            )
        ):
            diagnostics.append(
                _diagnostic(
                    "physics.non_finite_parameter",
                    "physics",
                    f"rigid:{body.index}:{body.name}",
                    "Rigid body has non-finite physics parameters",
                )
            )
    for joint in joints:
        if (
            joint.body_a < -1
            or joint.body_b < -1
            or joint.body_a >= len(rigid_bodies)
            or joint.body_b >= len(rigid_bodies)
        ):
            diagnostics.append(
                _diagnostic(
                    "physics.invalid_joint_body",
                    "physics",
                    f"joint:{joint.index}:{joint.name}",
                    "Joint refers to a missing rigid body",
                    bodies=(joint.body_a, joint.body_b),
                )
            )
        if any(low > high for low, high in zip(joint.minimum, joint.maximum, strict=True)):
            diagnostics.append(
                _diagnostic(
                    "physics.reversed_limits",
                    "physics",
                    f"joint:{joint.index}:{joint.name}",
                    "Joint limit minimum exceeds maximum",
                )
            )
        if any(not math.isfinite(value) for value in (*joint.minimum, *joint.maximum)):
            diagnostics.append(
                _diagnostic(
                    "physics.non_finite_limit",
                    "physics",
                    f"joint:{joint.index}:{joint.name}",
                    "Joint contains non-finite limit values",
                )
            )
    return diagnostics


# {
# 責務: [_diagnostic: PMX doctorの関連処理を実行する]
# 処理: [入力を検証し、安全な結果を返す]
# 引数: [code, category, target, message: 呼び出しに必要な値]
# 戻り値: [PmxDiagnostic: 処理結果]
# }
def _diagnostic(code: str, category: str, target: str, message: str, **evidence) -> PmxDiagnostic:
    return PmxDiagnostic(
        code, category, DiagnosticSeverity.ERROR, target, message, tuple(sorted(evidence.items()))
    )
