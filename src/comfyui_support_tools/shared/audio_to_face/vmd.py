"""VMD morph-track reader/writer and non-destructive facial merge."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path

from .contracts import MorphKey

VMD_HEADER = b"Vocaloid Motion Data 0002"
MAX_VMD_BYTES = 512 * 1024 * 1024
MAX_RECORDS = 5_000_000
MORPH_RECORD_SIZE = 23


# {
# 責務: [VmdFormatError: malformed VMD documentを表す]
# フィールド: [ValueError]
# 処理: [truncated sectionやinvalid morph recordを報告する]
# }
class VmdFormatError(ValueError):
    pass


# {
# 責務: [VmdDocument: preserved body/camera VMD sectionsとmorph trackを保持する]
# フィールド: [header, name, prefix, morphs, suffix]
# 処理: [morphだけ変更して他sectionを保持したままserializeする]
# }
@dataclass(frozen=True)
class VmdDocument:
    header: bytes
    model_name: bytes
    prefix: bytes
    morphs: tuple[MorphKey, ...]
    suffix: bytes


# {
# 責務: [read_vmd: filesystem VMDをparseする]
# 処理: [source bytesをloadしてbinary parserへ渡す]
# 引数: [path: VMD source path]
# 戻り値: [VmdDocument: parsed VMD sections]
# }
def read_vmd(path: str | Path) -> VmdDocument:
    source = Path(path)
    size = source.stat().st_size
    if size <= 0 or size > MAX_VMD_BYTES:
        raise VmdFormatError(f"VMD file size must be between 1 and {MAX_VMD_BYTES}")
    data = source.read_bytes()
    if len(data) != size:
        raise VmdFormatError("VMD file changed while it was being read")
    return read_vmd_bytes(data)


# {
# 責務: [read_vmd_bytes: byte string内のVMD sectionsをparseする]
# 処理: [1: header/bone/morph sectionsを検査, 2: trailing sectionsをvalidate]
# 引数: [data: VMD file bytes]
# 戻り値: [VmdDocument: parsed VMD sections]
# }
def read_vmd_bytes(data: bytes) -> VmdDocument:
    if len(data) <= 0 or len(data) > MAX_VMD_BYTES:
        raise VmdFormatError(f"VMD file size must be between 1 and {MAX_VMD_BYTES}")
    if len(data) < 58 or not data[:30].startswith(VMD_HEADER):
        raise VmdFormatError("unsupported or truncated VMD header")
    offset = 50
    bone_count = _read_count(data, offset, "bone")
    offset += 4
    prefix_end = offset + bone_count * 111
    if prefix_end + 4 > len(data):
        raise VmdFormatError("truncated VMD bone section")
    prefix = data[50:prefix_end]
    offset = prefix_end
    morph_count = _read_count(data, offset, "morph")
    offset += 4
    morph_end = offset + morph_count * MORPH_RECORD_SIZE
    if morph_end > len(data):
        raise VmdFormatError("truncated VMD morph section")
    morphs = []
    for index in range(morph_count):
        start = offset + index * MORPH_RECORD_SIZE
        raw_name = data[start : start + 15].split(b"\0", 1)[0]
        try:
            name = raw_name.decode("shift_jis", errors="strict")
        except UnicodeDecodeError as error:
            raise VmdFormatError(f"invalid morph name at record {index}") from error
        frame, weight = struct.unpack_from("<If", data, start + 15)
        if not math.isfinite(weight):
            raise VmdFormatError(f"non-finite morph weight at record {index}")
        morphs.append(MorphKey(name, frame, weight))
    suffix = data[morph_end:]
    _validate_suffix(suffix)
    return VmdDocument(data[:30], data[30:50], prefix, tuple(morphs), suffix)


# {
# 責務: [write_vmd: preserved VMD sectionsと更新morph trackをserializeする]
# 処理: [prefix/morph/suffixを順番に組み直す]
# 引数: [document, morphs: parsed VMD and output morph keys]
# 戻り値: [bytes: updated VMD file]
# }
def write_vmd(document: VmdDocument, morphs: tuple[MorphKey, ...]) -> bytes:
    records = _encode_morphs(morphs)
    return (
        document.header
        + document.model_name
        + document.prefix
        + struct.pack("<I", len(morphs))
        + records
        + document.suffix
    )


# {
# 責務: [write_facial_vmd: morph-only VMD documentを生成する]
# 処理: [empty bone and scene sectionsとrequested morph keysをserialize]
# 引数: [morphs, model_name: facial animation and target model]
# 戻り値: [bytes: facial VMD file]
# }
def write_facial_vmd(morphs: tuple[MorphKey, ...], model_name: str = "") -> bytes:
    if not morphs:
        raise ValueError("facial VMD requires at least one morph key")
    model = model_name.encode("shift_jis", errors="strict")[:20].ljust(20, b"\0")
    prefix = VMD_HEADER.ljust(30, b"\0") + model + struct.pack("<I", 0)
    suffix = b"".join(struct.pack("<I", 0) for _ in range(4))
    document = VmdDocument(prefix[:30], model, prefix[50:], (), suffix)
    return write_vmd(document, morphs)


# {
# 責務: [merge_facial_vmd: facial VMD morph keysをbody VMDへmergeする]
# 処理: [body sectionsを維持し指定policyで同名同frame morphをmerge]
# 引数: [body_vmd, facial_vmd, mode: input VMDs and conflict strategy]
# 戻り値: [bytes: merged VMD file]
# }
def merge_facial_vmd(
    body_vmd: str | Path,
    facial_vmd: str | Path,
    *,
    mode: str = "max",
) -> bytes:
    if mode not in {"max", "add", "replace"}:
        raise ValueError("morph merge mode must be max, add, or replace")
    body = read_vmd(body_vmd)
    face = read_vmd(facial_vmd)
    return merge_vmd_documents(body, face, mode)


# {
# 責務: [merge_vmd_documents: parsed facial documentをbody documentへmergeする]
# 処理: [same morph/frame conflict policyを適用してbody sectionsをserialize]
# 引数: [body, face, mode: VMD documents and merge strategy]
# 戻り値: [bytes: merged VMD file]
# }
def merge_vmd_documents(body: VmdDocument, face: VmdDocument, mode: str = "max") -> bytes:
    if mode not in {"max", "add", "replace"}:
        raise ValueError("morph merge mode must be max, add, or replace")
    combined: dict[tuple[str, int], float] = {
        (key.name, key.frame): key.weight for key in body.morphs
    }
    for key in face.morphs:
        identity = (key.name, key.frame)
        previous = combined.get(identity)
        if previous is None or mode == "replace":
            value = key.weight
        elif mode == "max":
            value = max(previous, key.weight)
        else:
            value = previous + key.weight
        combined[identity] = min(1.0, max(0.0, value))
    keys = tuple(MorphKey(name, frame, weight) for (name, frame), weight in combined.items())
    return write_vmd(body, keys)


# {
# 責務: [_read_count: VMD section countをbounds/limit checkする]
# 処理: [offsetからuint32を読みrecord上限を検証する]
# 引数: [data, offset, label: input bytes and section identity]
# 戻り値: [int: section record count]
# }
def _read_count(data: bytes, offset: int, label: str) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise VmdFormatError(f"truncated VMD {label} count")
    value = struct.unpack_from("<I", data, offset)[0]
    if value > MAX_RECORDS:
        raise VmdFormatError(f"VMD {label} count exceeds limit: {value}")
    return value


# {
# 責務: [_encode_morphs: morph tracksをVMD fixed recordへencodeする]
# 処理: [frame/name順へsortしShift-JIS/name/frame/weightを書き出す]
# 引数: [morphs: morph keyframes]
# 戻り値: [bytes: encoded VMD morph section]
# }
def _encode_morphs(morphs: tuple[MorphKey, ...]) -> bytes:
    ordered = sorted(morphs, key=lambda key: (key.frame, key.name.casefold()))
    output = bytearray()
    for key in ordered:
        name = key.name.encode("shift_jis", errors="strict")
        if (
            len(name) > 15
            or key.frame < 0
            or key.frame > 0xFFFFFFFF
            or not math.isfinite(key.weight)
        ):
            raise ValueError(f"invalid VMD morph key: {key.name!r} at frame {key.frame}")
        output.extend(name.ljust(15, b"\0"))
        output.extend(struct.pack("<If", key.frame, key.weight))
    return bytes(output)


# {
# 責務: [_validate_suffix: VMD camera/light/shadow/IK sectionsをvalidateする]
# 処理: [record countsとfixed/variable recordsがbyte範囲内か確認する]
# 引数: [suffix: bytes after morph records]
# 戻り値: [None: malformed dataはVmdFormatError]
# }
def _validate_suffix(suffix: bytes) -> None:
    offset = 0

    # {
    # 責務: [take: audio-to-face処理を実行する]
    # 処理: [入力を検証し、再現可能なfacial motion結果を返す]
    # 引数: [size: 処理入力]
    # 戻り値: [bytes: 処理結果]
    # }
    def take(size: int) -> bytes:
        nonlocal offset
        if offset + size > len(suffix):
            raise VmdFormatError("truncated VMD trailing section")
        result = suffix[offset : offset + size]
        offset += size
        return result

    for label, record_size in (("camera", 61), ("light", 28), ("self shadow", 9)):
        if offset == len(suffix):
            return
        count = struct.unpack("<I", take(4))[0]
        if count > MAX_RECORDS:
            raise VmdFormatError(f"VMD {label} count exceeds limit: {count}")
        take(count * record_size)
    if offset < len(suffix):
        display_count = struct.unpack("<I", take(4))[0]
        if display_count > MAX_RECORDS:
            raise VmdFormatError(f"VMD display count exceeds limit: {display_count}")
        for _ in range(display_count):
            take(5)
            ik_count = struct.unpack("<I", take(4))[0]
            if ik_count > MAX_RECORDS:
                raise VmdFormatError(f"VMD IK count exceeds limit: {ik_count}")
            take(ik_count * 21)
    if offset != len(suffix):
        raise VmdFormatError("unexpected trailing bytes after VMD sections")
