"""Automatic part masks and preservation-safe local compositing."""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from comfyui_support_tools.shared.contracts.expression_retouch import (
    DetectedFace,
    FacePart,
    NormalizedBox,
)

MAX_PIXELS = 80_000_000


# {
#   責務: [_region_box: resolve an automatic region request to detected face geometry]
#   処理: [1: expand the eyes group, 2: collect matching part rectangles]
#   引数: [face: selected detection, parts: user-selected edit parts]
#   戻り値: [tuple[NormalizedBox, ...]: normalized local regions]
# }
def _region_boxes(face: DetectedFace, parts: tuple[FacePart, ...]) -> tuple[NormalizedBox, ...]:
    available = {region.part: region.bbox for region in face.parts}
    selected = set(parts)
    if FacePart.FULL_FACE in selected:
        return (available[FacePart.FULL_FACE],)
    if FacePart.EYES in selected:
        selected.update((FacePart.LEFT_EYE, FacePart.RIGHT_EYE))
    missing = selected - available.keys()
    if missing:
        raise ValueError(
            f"face detector has no geometry for requested regions: {sorted(x.value for x in missing)}"
        )
    return tuple(available[part] for part in FacePart if part in selected)


# {
#   責務: [create_edit_mask: build a feathered local edit mask for one face]
#   処理: [1: validate canvas and face selection, 2: union automatic part regions or use manual refinement, 3: feather boundaries]
#   引数: [image_size: source canvas dimensions, face: selected face, parts: edit regions, manual_mask: optional user-refined grayscale PNG]
#   戻り値: [bytes: grayscale PNG mask where white permits editing]
# }
def create_edit_mask(
    image_size: tuple[int, int],
    face: DetectedFace,
    parts: tuple[FacePart, ...],
    manual_mask: bytes | None = None,
) -> bytes:
    width, height = image_size
    if width < 1 or height < 1 or width * height > MAX_PIXELS:
        raise ValueError("mask canvas must be positive and at most 80 megapixels")
    if manual_mask is not None:
        try:
            with Image.open(io.BytesIO(manual_mask)) as image:
                if image.size != image_size:
                    raise ValueError("manual mask dimensions must match the source image")
                mask = image.convert("L")
                mask.load()
        except (OSError, Image.DecompressionBombError) as error:
            raise ValueError("manual mask image is malformed or unsafe") from error
        if mask.getbbox() is None:
            raise ValueError("manual mask must select at least one pixel")
    else:
        mask = Image.new("L", image_size, 0)
        draw = ImageDraw.Draw(mask)
        for x, y, box_width, box_height in _region_boxes(face, parts):
            # Elliptical masks avoid rectangular edges around eyes, mouth, and cheeks.
            draw.ellipse(
                (
                    round(x * width),
                    round(y * height),
                    round((x + box_width) * width),
                    round((y + box_height) * height),
                ),
                fill=255,
            )
        if mask.getbbox() is None:
            raise ValueError("selected face regions did not produce an editable area")
    feather = max(1, min(32, round(min(width, height) * 0.008)))
    mask = mask.filter(ImageFilter.GaussianBlur(feather))
    output = io.BytesIO()
    mask.save(output, format="PNG", optimize=True)
    return output.getvalue()


# {
#   責務: [composite_local_edit: guarantee pixels outside a local edit mask stay unchanged]
#   処理: [1: decode same-size RGB images and grayscale mask, 2: alpha composite the edited pixels]
#   引数: [source: original image bytes, candidate: model output bytes, mask_bytes: feathered edit mask]
#   戻り値: [bytes: locally composited PNG]
# }
def composite_local_edit(source: bytes, candidate: bytes, mask_bytes: bytes) -> bytes:
    original = _decode_rgb(source)
    edited = _decode_rgb(candidate)
    with Image.open(io.BytesIO(mask_bytes)) as mask_source:
        if mask_source.size != original.size:
            raise ValueError("edit mask dimensions must match the source")
        mask = mask_source.convert("L")
        mask.load()
    if edited.size != original.size:
        raise ValueError("candidate dimensions must match the source image")
    output = Image.composite(edited, original, mask)
    stream = io.BytesIO()
    output.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


# {
#   責務: [_decode_rgb: validate and detach an image as bounded RGB pixels]
#   処理: [1: decode encoded bytes, 2: apply orientation, 3: enforce dimensions and convert]
#   引数: [content: encoded image]
#   戻り値: [Image.Image: detached RGB raster]
# }
def _decode_rgb(content: bytes) -> Image.Image:
    if not isinstance(content, bytes) or not 1 <= len(content) <= 64 * 1024 * 1024:
        raise ValueError("image must contain 1..64 MiB")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.width < 1 or image.height < 1 or image.width * image.height > MAX_PIXELS:
                raise ValueError("image dimensions exceed safe limits")
            image.load()
            return image.convert("RGB")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("image is malformed or unsafe") from error


# {
#   責務: [measure_candidate_preservation: compute measured non-target and locality proxies]
#   処理: [1: compare candidate pixels to source, 2: weight differences inside/outside the edit mask, 3: report evaluator absence]
#   引数: [source: original RGB image, candidate: raw model candidate, mask_bytes: allowed edit area]
#   戻り値: [tuple[float, float, tuple[str, ...]]: identity proxy, locality score, limitations]
# }
def measure_candidate_preservation(
    source: bytes, candidate: bytes, mask_bytes: bytes
) -> tuple[float, float, tuple[str, ...]]:
    original = _decode_rgb(source)
    edited = _decode_rgb(candidate)
    if original.size != edited.size:
        raise ValueError("candidate dimensions must match the source image")
    with Image.open(io.BytesIO(mask_bytes)) as mask_image:
        if mask_image.size != original.size:
            raise ValueError("mask dimensions must match the source image")
        mask = np.asarray(mask_image.convert("L"), dtype=np.float32) / 255
    before = np.asarray(original, dtype=np.float32)
    after = np.asarray(edited, dtype=np.float32)
    difference = np.max(np.abs(before - after), axis=2) / 255
    active = mask >= 0.15
    outside = ~active
    changed = difference >= 0.02
    non_target = 1.0 - float(difference[outside].mean()) if outside.any() else 1.0
    changed_count = int(changed.sum())
    locality = float((changed & active).sum()) / changed_count if changed_count else 0.0
    limitations = (
        "Expression match, face identity embeddings, and artifact quality require an optional semantic evaluator.",
        "Identity preservation is a pixel-difference proxy outside the selected mask, not biometric verification.",
    )
    return max(0.0, min(1.0, non_target)), max(0.0, min(1.0, locality)), limitations
