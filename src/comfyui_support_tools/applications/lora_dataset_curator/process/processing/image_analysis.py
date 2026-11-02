"""Read-only image inventory and conservative perceptual feature extraction."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from comfyui_support_tools.shared.contracts.dataset_curator import (
    ImageEvidenceProvider,
    ImageFeatures,
)

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"})
MAX_IMAGE_BYTES = 256 * 1024 * 1024


# {
# 責務: [_hash_file: compute an exact source image fingerprint]
# 処理: [stream file bytes into SHA-256 without loading the full image into memory]
# 引数: [path: regular local image file]
# 戻り値: [str: lowercase SHA-256 hex digest]
# }
def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# {
# 責務: [_perceptual_hash: create a compact grayscale average hash]
# 処理: [normalize orientation, downsample to 8x8 and compare pixels with the median]
# 引数: [image: decoded source image]
# 戻り値: [str: 64-bit average hash encoded as 16 hexadecimal characters]
# }
def _perceptual_hash(image: Image.Image) -> str:
    pixels = np.asarray(
        image.convert("L").resize((8, 8), Image.Resampling.LANCZOS), dtype=np.float32
    )
    median = float(np.median(pixels))
    bits = sum(int(value >= median) << index for index, value in enumerate(pixels.flat))
    return f"{bits:016x}"


# {
# 責務: [_quality_proxies: estimate blur, compression blocking and aspect preservation]
# 処理: [measure normalized Laplacian variance, 8-pixel boundary contrast and aspect-ratio loss]
# 引数: [image: decoded source image, width: oriented image width, height: oriented image height]
# 戻り値: [tuple[float, float, float]: blur sharpness, blocking artifact proxy and crop preservation score]
# }
def _quality_proxies(image: Image.Image, width: int, height: int) -> tuple[float, float, float]:
    gray = np.asarray(
        image.convert("L").resize((128, 128), Image.Resampling.BILINEAR), dtype=np.float32
    )
    laplacian = (
        -4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    blur = min(1.0, math.log1p(float(laplacian.var())) / math.log1p(2000))
    vertical = np.abs(np.diff(gray, axis=1))
    horizontal = np.abs(np.diff(gray, axis=0))
    boundary = np.concatenate((vertical[:, 7::8].ravel(), horizontal[7::8, :].ravel()))
    interior = np.concatenate((vertical[:, 1::8].ravel(), horizontal[1::8, :].ravel()))
    ratio = float(boundary.mean()) / max(float(interior.mean()), 1e-6)
    blocking = min(1.0, max(0.0, (ratio - 1.0) * 2.0))
    crop = min(width, height) / max(width, height)
    return blur, blocking, crop


# {
# 責務: [inspect_image: inventory one image without modifying its source]
# 処理: [validate path and size, decode oriented pixels, hash, measure quality proxies and optional vision evidence, then detect concurrent changes]
# 引数: [source: image file, evidence_provider: optional face/body/concept analyzer]
# 戻り値: [ImageFeatures: dimensions, exact/perceptual hashes, measured proxies and optional evidence]
# エラー: [ValueError: file is unsupported, oversized, or not a valid image, RuntimeError: image changed during inspection]
# }
def inspect_image(
    source: str | Path, evidence_provider: ImageEvidenceProvider | None = None
) -> ImageFeatures:
    original = Path(source).expanduser()
    if original.is_symlink():
        raise ValueError("dataset image cannot be a symbolic link")
    path = original.resolve(strict=True)
    before = path.stat()
    if (
        not path.is_file()
        or path.suffix.casefold() not in IMAGE_EXTENSIONS
        or before.st_size <= 0
        or before.st_size > MAX_IMAGE_BYTES
    ):
        raise ValueError("dataset image must be a supported, nonempty file below 256 MiB")
    try:
        with Image.open(path) as decoded:
            decoded.verify()
        with Image.open(path) as decoded:
            oriented = ImageOps.exif_transpose(decoded).convert("RGB")
            width, height = oriented.size
            if width < 16 or height < 16 or width * height > 150_000_000:
                raise ValueError("image dimensions exceed safe analysis limits")
            perceptual = _perceptual_hash(oriented)
            blur, compression, crop = _quality_proxies(oriented, width, height)
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError(f"cannot safely decode dataset image {path.name}") from error
    face_visibility = body_visibility = None
    concept_match = None
    if evidence_provider:
        evidence = evidence_provider.analyze(path)
        if not isinstance(evidence, tuple) or len(evidence) != 3:
            raise ValueError("image evidence provider must return face/body/concept evidence")
        face_visibility, body_visibility, concept_match = evidence
        for value in (face_visibility, body_visibility):
            if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError("vision visibility evidence must be normalized to 0..1")
        if concept_match is not None and not isinstance(concept_match, bool):
            raise ValueError("concept match evidence must be boolean or unknown")
    exact_hash = _hash_file(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("dataset image changed while it was being inspected")
    return ImageFeatures(
        width,
        height,
        exact_hash,
        perceptual,
        blur,
        compression,
        crop,
        face_visibility,
        body_visibility,
        concept_match,
    )
