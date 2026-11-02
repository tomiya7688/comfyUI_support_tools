"""Write and verify a transparency record in a non-destructive PNG copy."""

import json
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw
from PIL.PngImagePlugin import PngInfo

PNG_PROVENANCE_KEY = "comfyui_support_tools.transparency"


# {
# 責務: [ _has_c2pa_jumbf: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [data]
# 戻り値: [処理結果]
# }
def _has_c2pa_jumbf(data: bytes) -> bool:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("input is not a valid PNG signature")
    offset = 8
    while offset + 12 <= len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + length
        if end > len(data):
            raise ValueError("PNG contains a truncated chunk")
        kind = data[offset + 4 : offset + 8]
        if kind == b"caBX":
            return True
        offset = end
        if kind == b"IEND":
            return False
    raise ValueError("PNG is missing a complete IEND chunk")


# {
# 責務: [ create_png_transparency_copy: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [source_path, payload, visible_disclosure_label]
# 戻り値: [処理結果]
# }
def create_png_transparency_copy(
    source_path: str | Path,
    payload: dict,
    *,
    visible_disclosure_label: str | None = None,
) -> bytes:
    """Return a PNG with machine-readable metadata, preserving the source file."""
    source = Path(source_path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("PNG source must be a regular file")
    raw = source.read_bytes()
    if _has_c2pa_jumbf(raw):
        raise ValueError(
            "PNG already contains C2PA credentials; use the C2PA adapter to preserve them"
        )
    with Image.open(BytesIO(raw)) as image:
        if image.format != "PNG":
            raise ValueError("native transparency metadata currently supports PNG only")
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("animated PNG metadata export is not supported")
        source_info = dict(image.info)
        if visible_disclosure_label:
            if visible_disclosure_label not in {"AI-generated", "AI-assisted"}:
                raise ValueError("unsupported visible disclosure label")
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA")
            draw = ImageDraw.Draw(image, "RGBA")
            padding = max(5, image.width // 100)
            bounds = draw.textbbox((0, 0), visible_disclosure_label)
            text_width = bounds[2] - bounds[0]
            text_height = bounds[3] - bounds[1]
            if text_width + padding * 4 > image.width or text_height + padding * 4 > image.height:
                raise ValueError("PNG is too small for the requested visible disclosure label")
            right = image.width - padding
            bottom = image.height - padding
            left = max(padding, right - text_width - padding * 2)
            top = max(padding, bottom - text_height - padding * 2)
            draw.rectangle((left, top, right, bottom), fill=(0, 0, 0, 160))
            draw.text(
                (left + padding, top + padding), visible_disclosure_label, fill=(255, 255, 255, 255)
            )
        metadata = PngInfo()
        for key, value in source_info.items():
            if key == PNG_PROVENANCE_KEY or not isinstance(value, (str, bytes)):
                continue
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            metadata.add_text(key, value)
        metadata.add_text(
            PNG_PROVENANCE_KEY,
            json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False),
        )
        output = BytesIO()
        save_options = {"format": "PNG", "pnginfo": metadata}
        for key in ("icc_profile", "exif", "dpi", "transparency"):
            if key in source_info:
                save_options[key] = source_info[key]
        image.save(output, **save_options)
    return output.getvalue()


# {
# 責務: [ verify_png_transparency: 入力を処理して結果を返す ]
# 処理: [ 1: 入力を検証・処理する, 2: 結果を返す ]
# 引数: [data, expected_payload]
# 戻り値: [処理結果]
# }
def verify_png_transparency(data: bytes, expected_payload: dict) -> bool:
    try:
        with Image.open(BytesIO(data)) as image:
            stored = json.loads(image.info[PNG_PROVENANCE_KEY])
    except (KeyError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return stored == expected_payload
