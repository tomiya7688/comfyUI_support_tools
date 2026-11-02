"""OpenCV cascade face detection and normalized facial-part regions."""

from __future__ import annotations

import io
import math

import cv2
import numpy as np
from PIL import Image, ImageOps

from comfyui_support_tools.shared.contracts.expression_retouch import (
    DetectedFace,
    FaceAnalysis,
    FacePart,
    FacePartRegion,
)

MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 80_000_000
MAX_DETECTOR_EDGE = 1600


# {
#   責務: [_decode_image: safely decode one source image for face analysis]
#   処理: [1: bound input bytes, 2: apply EXIF orientation, 3: enforce pixel limit]
#   引数: [source: encoded image bytes]
#   戻り値: [Image.Image: detached RGB image]
# }
def _decode_image(source: bytes) -> Image.Image:
    if not isinstance(source, bytes) or not 1 <= len(source) <= MAX_IMAGE_BYTES:
        raise ValueError("source image must contain 1..64 MiB")
    try:
        with Image.open(io.BytesIO(source)) as image:
            image = ImageOps.exif_transpose(image)
            if image.width < 1 or image.height < 1 or image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("source image exceeds the 80 megapixel limit")
            image.load()
            return image.convert("RGB")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("source image is malformed or unsafe") from error


# {
#   責務: [normalize_source_image: store an orientation-corrected PNG source copy]
#   処理: [1: safely decode image, 2: encode detached RGB raster as PNG]
#   引数: [source: original encoded image bytes]
#   戻り値: [bytes: canonical PNG image]
# }
def normalize_source_image(source: bytes) -> bytes:
    image = _decode_image(source)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


# {
#   責務: [_part_regions: estimate normalized facial part regions from a face box]
#   処理: [1: map eye, brow, mouth, cheek and tear regions to face-relative coordinates]
#   引数: [box: normalized detected face rectangle]
#   戻り値: [tuple[FacePartRegion, ...]: approximate editable regions]
#   補足: [Haar cascade detects the face box; facial-part regions are geometric estimates, not landmarks]
# }
def _part_regions(box: tuple[float, float, float, float]) -> tuple[FacePartRegion, ...]:
    x, y, width, height = box
    regions = {
        FacePart.FULL_FACE: (0.08, 0.04, 0.84, 0.92),
        FacePart.LEFT_EYE: (0.16, 0.29, 0.27, 0.15),
        FacePart.RIGHT_EYE: (0.57, 0.29, 0.27, 0.15),
        FacePart.EYEBROWS: (0.13, 0.17, 0.75, 0.15),
        FacePart.MOUTH: (0.29, 0.65, 0.42, 0.20),
        FacePart.CHEEKS: (0.12, 0.49, 0.76, 0.26),
        FacePart.TEAR_REGION: (0.12, 0.38, 0.76, 0.35),
    }
    return tuple(
        FacePartRegion(
            part,
            (x + rx * width, y + ry * height, rw * width, rh * height),
            0.35,
        )
        for part, (rx, ry, rw, rh) in regions.items()
    )


# {
#   責務: [analyze_faces: detect and stably order faces in a source image]
#   処理: [1: decode and downscale a copy, 2: run frontal Haar cascade, 3: normalize boxes and estimate face parts]
#   引数: [source: encoded input image]
#   戻り値: [FaceAnalysis: detections and honest detector limitations]
# }
def analyze_faces(source: bytes) -> FaceAnalysis:
    image = _decode_image(source)
    width, height = image.size
    scale = min(1.0, MAX_DETECTOR_EDGE / max(width, height))
    analysis_image = image.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.LANCZOS
    )
    pixels = np.asarray(analysis_image)
    gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        raise RuntimeError("OpenCV frontal-face cascade could not be loaded")
    try:
        boxes, _reject, weights = cascade.detectMultiScale3(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24), outputRejectLevels=True
        )
        confidences = [
            1.0 / (1.0 + math.exp(-max(-12.0, min(12.0, float(value))))) for value in weights
        ]
    except AttributeError:
        boxes = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        confidences = [0.5] * len(boxes)
    scale_x = width / analysis_image.width
    scale_y = height / analysis_image.height
    normalized = sorted(
        (
            (
                x * scale_x / width,
                y * scale_y / height,
                box_width * scale_x / width,
                box_height * scale_y / height,
                confidence,
            )
            for (x, y, box_width, box_height), confidence in zip(boxes, confidences, strict=True)
        ),
        key=lambda item: (item[0], item[1]),
    )
    faces = tuple(
        DetectedFace(
            index,
            (x, y, face_width, face_height),
            confidence,
            _part_regions((x, y, face_width, face_height)),
        )
        for index, (x, y, face_width, face_height, confidence) in enumerate(normalized)
    )
    warnings = [
        "Facial part boxes are approximate face-relative regions; no landmark model is installed."
    ]
    if any(face.bbox[2] * width < 48 or face.bbox[3] * height < 48 for face in faces):
        warnings.append(
            "At least one detected face is low-resolution; part selection may be inaccurate."
        )
    return FaceAnalysis((width, height), faces, tuple(warnings))
