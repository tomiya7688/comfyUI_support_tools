"""Explainable blur and clipping estimates for capture guidance."""

from __future__ import annotations

from PIL import Image, ImageFilter, ImageStat

from .contracts import CaptureFrame, CaptureQuality


# {
#   責務: [score_capture_quality: image focus proxy and clippingからper-frame qualityを評価する]
#   処理: [measure edge energy and near-black/near-white pixels with named metrics]
#   引数: [frame: imported or decoded capture observation]
#   戻り値: [CaptureQuality: score, blur proxy, clipping fraction and guidance warnings]
# }
def score_capture_quality(frame: CaptureFrame, image: Image.Image | None = None) -> CaptureQuality:
    if image is None:
        raise ValueError("capture frame must be decoded before quality scoring")
    image = image.convert("RGB")
    grayscale = image.convert("L")
    edge_energy = ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES)).var[0]
    blur_proxy = max(0.0, float(edge_energy))
    histogram = grayscale.histogram()
    pixel_count = image.width * image.height
    clipped = (sum(histogram[:5]) + sum(histogram[251:])) / pixel_count
    focus_score = min(1.0, blur_proxy / 800.0)
    score = max(0.0, min(1.0, focus_score * (1.0 - min(1.0, clipped * 2.0))))
    warnings = []
    if blur_proxy < 12:
        warnings.append("low_edge_energy_possible_blur")
    if clipped > 0.08:
        warnings.append("significant_highlight_or_shadow_clipping")
    return CaptureQuality(frame.relative_path, score, blur_proxy, clipped, tuple(warnings))


# {
#   責務: [score_capture_set: capture set全frameの品質値を算出する]
#   処理: [preserve source ordering for side-by-side review]
#   引数: [frames: imported capture frames]
#   戻り値: [tuple[CaptureQuality, ...]: per-frame diagnostics]
# }
def score_capture_set(
    frames: tuple[CaptureFrame, ...], images: tuple[Image.Image, ...]
) -> tuple[CaptureQuality, ...]:
    return tuple(
        score_capture_quality(frame, image) for frame, image in zip(frames, images, strict=True)
    )
