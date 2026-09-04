import argparse
import sys
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from image_enhancer import EnhanceSettings, process_image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
OBJECT_PRESETS = {
    "generic": (10, 1.2), "clothing": (7, 2.0), "cloth": (5, 2.4),
    "shirt": (7, 2.1), "bra": (8, 1.5), "panties": (8, 1.5), "carpet": (4, 2.8),
    "skin": (6, 1.1), "ribbon": (14, 0.7), "regular": (12, 0.8), "solid": (9, 1.5),
}
SURFACE_PRESETS = {
    "auto": 1.00,
    "thin_cloth": 1.12,
    "t_shirt": 0.96,
    "thick_cloth": 0.78,
    "thin_paper": 0.90,
    "clear_film": 0.68,
}

def surface_alpha_for(alpha, surface_preset):
    scale = SURFACE_PRESETS.get(surface_preset, SURFACE_PRESETS["auto"])
    return max(0.05, min(0.30, float(alpha) * scale))

def estimate_surface_color(rgb):
    import cv2, numpy as np
    lab_image = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    height, width = lab_image.shape[:2]; margin = max(1, min(height, width) // 10)
    border = np.concatenate((lab_image[:margin].reshape(-1, 3), lab_image[-margin:].reshape(-1, 3), lab_image[:, :margin].reshape(-1, 3), lab_image[:, -margin:].reshape(-1, 3)))
    lab = border.astype(np.float32)
    criteria=(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,20,1.0)
    _, _, centers = cv2.kmeans(lab, 4, None, criteria, 2, cv2.KMEANS_PP_CENTERS)
    centers = centers.astype(np.uint8); rgb_centers = cv2.cvtColor(centers.reshape(1,-1,3), cv2.COLOR_LAB2RGB).reshape(-1,3)
    return [tuple(int(v) for v in color) for color in rgb_centers]

def estimate_surface_alpha(rgb):
    import cv2, numpy as np
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    height, width = lab.shape[:2]; margin = max(1, min(height, width) // 10)
    border = np.concatenate((lab[:margin].reshape(-1, 3), lab[-margin:].reshape(-1, 3), lab[:, :margin].reshape(-1, 3), lab[:, -margin:].reshape(-1, 3))).astype(np.float32)
    spread = float(np.mean(np.std(border, axis=0)))
    return float(np.clip(0.28 - spread / 180.0, 0.08, 0.24))

def weaken_surface_component(rgb, clusters, alpha=0.16):
    import cv2, numpy as np
    colors = cv2.cvtColor(np.asarray(clusters, dtype=np.uint8).reshape(1, -1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    pixels_lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32); pixels = rgb.astype(np.float32)
    distance = np.sqrt(((pixels_lab[...,None,:] - colors[None,None,...])**2).sum(axis=3))
    nearest = np.argmin(distance, axis=2); surface_rgb = np.asarray(clusters, dtype=np.float32)[nearest]
    adaptive_alpha = alpha * np.exp(-(np.min(distance, axis=2) / 22.0) ** 2)
    corrected = ((pixels - adaptive_alpha[...,None] * surface_rgb) / (1.0 - adaptive_alpha[...,None])).clip(0,255)
    return corrected.astype("uint8")

def enhance_local_contrast(rgb):
    import cv2
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2RGB)

def reduce_low_frequency_shading(rgb, strength=0.45):
    import cv2, numpy as np
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    lightness, a, b = cv2.split(lab)
    low = cv2.GaussianBlur(lightness, (0, 0), 18.0)
    normalized = np.clip(lightness.astype(np.float32) - (low.astype(np.float32) - float(low.mean())) * strength, 0, 255).astype("uint8")
    return cv2.cvtColor(cv2.merge((normalized, a, b)), cv2.COLOR_LAB2RGB)

def shape_features(rgb):
    import cv2
    edges = cv2.Canny(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), 60, 150)
    contours, hierarchy = cv2.findContours(edges, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    areas = [cv2.contourArea(contour) for contour in contours if cv2.contourArea(contour) >= 12]
    elongated = 0
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if min(width, height) and max(width, height) / min(width, height) >= 3: elongated += 1
    holes = float(sum(1 for index, contour in enumerate(contours) if hierarchy is not None and hierarchy[0][index][3] >= 0 and cv2.contourArea(contour) >= 12))
    binary = (edges > 0).astype("uint8")
    mirrored = cv2.flip(binary, 1)
    symmetry = float((binary == mirrored).mean())
    return float(len(areas)), float(sum(areas)), float(elongated), holes, symmetry

def refine_object_mask(mask, preset):
    import cv2
    binary = (mask > 127).astype("uint8") * 255
    if preset in {"clothing", "cloth"}:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    elif preset == "shirt":
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    elif preset in {"bra", "panties"}:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    elif preset == "skin":
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    elif preset == "carpet":
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    elif preset == "ribbon":
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    elif preset == "regular":
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    elif preset == "solid":
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    return binary

def skeleton_features(mask):
    import cv2, numpy as np
    binary = (mask > 127).astype("uint8") * 255
    skeleton = np.zeros_like(binary)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    working = binary.copy()
    while cv2.countNonZero(working):
        opened = cv2.morphologyEx(working, cv2.MORPH_OPEN, element)
        skeleton = cv2.bitwise_or(skeleton, cv2.subtract(working, opened))
        working = cv2.erode(working, element)
    points = (skeleton > 0).astype("uint8")
    neighbors = cv2.filter2D(points, cv2.CV_16U, np.ones((3, 3), dtype="uint8")) - points
    endpoints = int(((points == 1) & (neighbors == 1)).sum())
    return float(points.sum()), float(endpoints)

def recommend_object_preset(mask):
    import cv2
    binary = (mask > 127).astype("uint8") * 255
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return "generic"
    contour = max(contours, key=cv2.contourArea)
    x, y, width, height = cv2.boundingRect(contour)
    aspect = max(width, height) / max(1, min(width, height))
    area_ratio = cv2.contourArea(contour) / max(1, mask.shape[0] * mask.shape[1])
    if aspect >= 3.0:
        return "ribbon"
    if area_ratio >= 0.45:
        return "solid"
    return "cloth" if aspect <= 1.8 else "regular"

def denoise_reference_image(image, enabled):
    if not enabled:
        return image
    import cv2
    if image.ndim == 2:
        return cv2.medianBlur(image, 3)
    if image.shape[2] == 4:
        return __import__("numpy").dstack((cv2.bilateralFilter(image[:, :, :3], 7, 40, 40), image[:, :, 3]))
    return cv2.bilateralFilter(image, 7, 40, 40)

def reference_shape_distance(first, second):
    import math
    area_distance = abs(math.log(max(first["area"], 1e-6) / max(second["area"], 1e-6)))
    aspect_distance = abs(math.log(max(first["aspect"], 1e-6) / max(second["aspect"], 1e-6)))
    return area_distance + aspect_distance * 0.5

def reference_shape_consistency(descriptors):
    import math
    if len(descriptors) < 2:
        return 1.0
    distances = []
    for index, first in enumerate(descriptors):
        for second in descriptors[index + 1:]:
            distances.append(reference_shape_distance(first, second))
    return 1.0 / (1.0 + sum(distances) / max(1, len(distances)))

def reference_shape_summary(reference_dir, denoise=False):
    import collections, cv2, numpy as np
    if reference_dir is None or not Path(reference_dir).is_dir():
        return {"preset": "generic", "image_count": 0, "confidence": 0.0, "distribution": {}}
    descriptors = []
    paths = sorted(path for path in Path(reference_dir).rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTS)
    for path in paths[:100]:
        image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
        if image is None: continue
        image = denoise_reference_image(image, denoise)
        if image.ndim == 3 and image.shape[2] == 4:
            mask = (image[:, :, 3] > 10).astype("uint8") * 255
        else:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
            edges = cv2.Canny(gray, 60, 150); contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours: continue
            mask = np.zeros_like(gray); cv2.drawContours(mask, [max(contours, key=cv2.contourArea)], -1, 255, thickness=cv2.FILLED)
        if cv2.countNonZero(mask) >= mask.size * 0.01:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours: continue
            contour = max(contours, key=cv2.contourArea)
            _, _, width, height = cv2.boundingRect(contour)
            descriptors.append({"preset": recommend_object_preset(mask), "area": cv2.contourArea(contour) / max(1, mask.size), "aspect": width / max(1, height)})
    if not descriptors:
        return {"preset": "generic", "image_count": 0, "confidence": 0.0, "distribution": {}, "common_object_count": 0, "common_shape_consistency": 0.0, "outlier_count": 0}
    groups = {}
    for descriptor in descriptors:
        groups.setdefault(descriptor["preset"], []).append(descriptor)
    ranked = []
    for preset, values in groups.items():
        clusters = [[candidate for candidate in values if reference_shape_distance(anchor, candidate) <= 0.55] for anchor in values]
        common = max(clusters, key=lambda cluster: (len(cluster), reference_shape_consistency(cluster)))
        ranked.append((preset, common, reference_shape_consistency(common)))
    preset, common, consistency = max(ranked, key=lambda item: (len(item[1]) * item[2], len(item[1]), item[2], item[0]))
    counts = collections.Counter(item["preset"] for item in descriptors)
    return {"preset": preset, "image_count": len(descriptors), "confidence": len(common) / len(descriptors), "distribution": dict(sorted(counts.items())), "common_object_count": len(common), "common_shape_consistency": consistency, "outlier_count": len(descriptors) - len(common)}

def reference_shape_hint(reference_dir, denoise=False):
    summary = reference_shape_summary(reference_dir, denoise)
    return summary["preset"], summary["image_count"]

def reference_surface_hint(reference_dir, denoise=False):
    import cv2, numpy as np
    if reference_dir is None or not Path(reference_dir).is_dir(): return None, None, 0
    colors, alphas = [], []
    paths = sorted(path for path in Path(reference_dir).rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTS)
    for path in paths[:100]:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None: continue
        image = denoise_reference_image(image, denoise)
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB); colors.extend(estimate_surface_color(rgb)); alphas.append(estimate_surface_alpha(rgb))
    if not colors: return None, None, 0
    samples = np.asarray(colors, dtype=np.float32); count = min(4, len(samples)); criteria=(cv2.TERM_CRITERIA_EPS+cv2.TERM_CRITERIA_MAX_ITER,20,1.0)
    _, _, centers = cv2.kmeans(samples, count, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    return [tuple(int(value) for value in color) for color in centers], float(np.mean(alphas)), len(alphas)

def settings_for(profile):
    values = {
        "color": (22,-12,5,5,68), "color_strong": (32,-18,7,9,82),
        "shape": (9,-5,9,24,64), "shape_strong": (14,-7,12,34,76),
        "balanced": (15,-10,10,12,65), "balanced_strong": (21,-13,12,19,73),
        "conservative": (5,-5,5,3,45), "observed_color": (16,-10,9,16,70), "observed_conservative": (7,-6,6,7,52),
    }
    contrast, highlights, shadows, detail, opacity = values.get(profile, values["balanced"])
    return EnhanceSettings(contrast=contrast, highlights=highlights, shadows=shadows, detail=detail, opacity=opacity, passes=1)

def correct_surface_image(image, surface_clusters, surface_alpha, profile):
    import numpy as np
    rgba = np.asarray(image.convert("RGBA"))
    rgb = rgba[..., :3].copy()
    if surface_clusters:
        rgb = weaken_surface_component(rgb, surface_clusters, surface_alpha)
    rgb = reduce_low_frequency_shading(rgb, 0.30 if profile == "conservative" else 0.45)
    rgb = enhance_local_contrast(rgb)
    return Image.fromarray(np.dstack((rgb, rgba[..., 3])), "RGBA")

def process_images(source: Path, target: Path, profile="balanced", object_preset="generic", reference_dir=None, surface_reference_dir=None, surface_preset="auto", denoise_reference=False):
    paths = [source] if source.is_file() and source.suffix.lower() in IMAGE_EXTS else sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
    if not paths:
        raise ValueError(f"画像ファイルが見つかりません: {source}")
    reference_preset, reference_image_count = reference_shape_hint(reference_dir, denoise_reference)
    if object_preset == "generic" and reference_preset != "generic":
        object_preset = reference_preset
        print(f"reference_shape_preset={object_preset} images={reference_image_count}", flush=True)
    reference_clusters, reference_alpha, reference_count = reference_surface_hint(surface_reference_dir, denoise_reference)
    if reference_clusters:
        print(f"reference_surface images={reference_count} alpha={surface_alpha_for(reference_alpha, surface_preset):.3f} preset={surface_preset}", flush=True)
    if source.is_file() and target.suffix:
        destinations = [(source, target)]
    else:
        target.mkdir(parents=True, exist_ok=True)
        destinations = [(path, target / (Path(path.name) if source.is_file() else path.relative_to(source))) for path in paths]
    for path, out in destinations:
        out.parent.mkdir(parents=True, exist_ok=True)
        image = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
        surface_clusters = reference_clusters or estimate_surface_color(np.asarray(image.convert("RGB")))
        source_alpha = reference_alpha if reference_alpha is not None else estimate_surface_alpha(np.asarray(image.convert("RGB")))
        surface_alpha = surface_alpha_for(source_alpha, surface_preset)
        prepared = correct_surface_image(image, surface_clusters, surface_alpha, profile)
        result = process_image(prepared, settings_for(profile))
        if out.suffix.lower() in {".jpg", ".jpeg"}: result = result.convert("RGB")
        result.save(out)
        print(f"processed: {path}", flush=True)

def process_video(source, target, profile="balanced", object_preset="generic", preview_seconds=0, roi=None, preview_start_seconds=0, reference_dir=None, surface_reference_dir=None, surface_preset="auto", denoise_reference=False):
    import subprocess, cv2, numpy as np
    if not source.is_file():
        raise ValueError(f"動画入力はファイルを指定してください: {source}")
    reference_preset, reference_image_count = reference_shape_hint(reference_dir, denoise_reference)
    if object_preset == "generic" and reference_preset != "generic":
        object_preset = reference_preset
        print(f"reference_shape_preset={object_preset} images={reference_image_count}", flush=True)
    reference_clusters, reference_alpha, reference_count = reference_surface_hint(surface_reference_dir, denoise_reference)
    if reference_clusters: print(f"reference_surface images={reference_count} alpha={surface_alpha_for(reference_alpha, surface_preset):.3f} preset={surface_preset}", flush=True)
    if target.exists() and target.is_dir():
        target = target / f"{source.stem}_enhanced.mp4"
    elif not target.suffix:
        target = target.with_suffix(".mp4")
    target.parent.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened(): raise ValueError(f"動画を開けません: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); preview_start_seconds = max(0.0, float(preview_start_seconds)); max_frames = int(fps * preview_seconds) if preview_seconds else 0
    if preview_start_seconds:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * preview_start_seconds))
    temp = target.with_name(target.stem + "_video_only.mp4"); writer=cv2.VideoWriter(str(temp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width,height))
    settings = settings_for(profile)
    object_mask = None; mask_preview_path = target.with_name(target.stem + "_mask.png"); previous_mask_array = None; previous_histogram = None; surface_clusters = reference_clusters; surface_alpha = surface_alpha_for(reference_alpha if reference_alpha is not None else 0.16, surface_preset); previous_gray = None; previous_analysis_rgb = None; observed_color_map = None; track_points = None; camera_points = None; tracking_confidence = 0.0; previous_output = None; previous_enhanced = None; flicker_sum = 0.0; information_gain = 0.0; edge_gain = 0.0; clipping = 0.0; deviation = 0.0; component_count = 0.0; component_area = 0.0; elongated_count = 0.0; hole_count = 0.0; symmetry_sum = 0.0; skeleton_length = 0.0; skeleton_endpoints = 0.0; skeleton_samples = 0; noise_sum = 0.0; halo_sum = 0.0; temporal_shape_sum = 0.0; scene_change_count = 0; mask_reinitialize_count = 0; track_reacquire_count = 0; tracking_confidence_sum = 0.0; camera_motion_sum = 0.0; target_motion_sum = 0.0; temporal_fusion_frames = 0; temporal_fusion_weight_sum = 0.0; observed_color_frames = 0
    count=0
    while True:
        ok, frame = cap.read()
        if not ok: break
        if max_frames and count >= max_frames: break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if count == 0 and surface_clusters is None:
            surface_clusters = estimate_surface_color(rgb); surface_alpha = surface_alpha_for(estimate_surface_alpha(rgb), surface_preset); print(f"surface_color_clusters={surface_clusters} surface_alpha={surface_alpha:.3f} preset={surface_preset}", flush=True)
        elif count % max(1, int(fps)) == 0:
            measured_alpha = surface_alpha_for(estimate_surface_alpha(rgb), surface_preset)
            surface_alpha = surface_alpha * 0.80 + measured_alpha * 0.20
        if surface_clusters:
            rgb = weaken_surface_component(rgb, surface_clusters, surface_alpha)
        rgb = reduce_low_frequency_shading(rgb, 0.30 if profile == "conservative" else 0.45)
        rgb = enhance_local_contrast(rgb)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        histogram = cv2.calcHist([gray], [0], None, [32], [0, 256]); cv2.normalize(histogram, histogram)
        if previous_histogram is not None and cv2.compareHist(previous_histogram, histogram, cv2.HISTCMP_BHATTACHARYYA) > 0.45:
            object_mask = None; track_points = None; camera_points = None; previous_enhanced = None; previous_analysis_rgb = None; observed_color_map = None
            scene_change_count += 1
            print(f"scene_change_reinitialize frame={count}", flush=True)
        previous_histogram = histogram
        frame_transform = None; frame_camera_motion = 0.0; frame_target_motion = 0.0
        analysis_rgb = rgb
        if object_mask is None:
            mask_reinitialize_count += 1
            seg = np.zeros((height, width), np.uint8); bgd=np.zeros((1,65),np.float64); fgd=np.zeros((1,65),np.float64)
            margin, blur = OBJECT_PRESETS[object_preset]
            rect = (int(roi[0]*width), int(roi[1]*height), max(2, int(roi[2]*width)), max(2, int(roi[3]*height))) if roi else (width*margin//100,height*margin//100,width*(100-margin*2)//100,height*(100-margin*2)//100)
            cv2.grabCut(rgb, seg, rect, bgd, fgd, 2, cv2.GC_INIT_WITH_RECT)
            raw_mask = np.where((seg==1)|(seg==3),255,0).astype("uint8")
            if object_preset == "generic":
                object_preset = recommend_object_preset(raw_mask)
                margin, blur = OBJECT_PRESETS[object_preset]
                print(f"auto_object_preset={object_preset}", flush=True)
            mask_array = refine_object_mask(raw_mask, object_preset); object_mask = Image.fromarray(mask_array)
            preview = rgb.copy(); preview[mask_array == 0] = (preview[mask_array == 0] * 0.25).astype("uint8"); cv2.imwrite(str(mask_preview_path), cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))
            track_points = cv2.goodFeaturesToTrack(gray, maxCorners=120, qualityLevel=0.01, minDistance=8, mask=mask_array); camera_points = cv2.goodFeaturesToTrack(gray, maxCorners=180, qualityLevel=0.01, minDistance=8); tracking_confidence = 1.0 if track_points is not None else 0.0
        elif previous_gray is not None and track_points is not None and len(track_points) >= 3:
            cam_matrix = None
            if camera_points is not None and len(camera_points) >= 3:
                cam_new, cam_status, _ = cv2.calcOpticalFlowPyrLK(previous_gray, gray, camera_points, None)
                old_cam = camera_points[cam_status.ravel() == 1]; new_cam = cam_new[cam_status.ravel() == 1]
                if len(new_cam) >= 3:
                    cam_matrix, _ = cv2.estimateAffinePartial2D(old_cam, new_cam, method=cv2.RANSAC)
                    if cam_matrix is not None: frame_camera_motion = float(np.linalg.norm(cam_matrix[:, 2]))
                    camera_points = new_cam.reshape(-1,1,2)
            new_points, status, _ = cv2.calcOpticalFlowPyrLK(previous_gray, gray, track_points, None)
            good_old = track_points[status.ravel() == 1]; good_new = new_points[status.ravel() == 1]
            if len(good_new) >= 3:
                backward, backward_status, _ = cv2.calcOpticalFlowPyrLK(gray, previous_gray, good_new.reshape(-1, 1, 2), None)
                if backward is not None:
                    round_trip_error = np.linalg.norm(backward.reshape(-1, 2) - good_old.reshape(-1, 2), axis=1)
                    reliable = (backward_status.ravel() == 1) & (round_trip_error <= 1.5)
                    good_old = good_old[reliable]; good_new = good_new[reliable]
            if len(good_new) >= 3:
                matrix, _ = cv2.estimateAffinePartial2D(good_old, good_new, method=cv2.RANSAC)
                if matrix is not None:
                    frame_transform = matrix
                    target_matrix = matrix.copy()
                    if cam_matrix is not None:
                        target_matrix[:, 2] -= cam_matrix[:, 2]
                    frame_target_motion = float(np.linalg.norm(target_matrix[:, 2]))
                    moved = cv2.warpAffine(np.asarray(object_mask), frame_transform, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                    previous_mask = np.asarray(object_mask, dtype=np.float32)
                    mask_array = (previous_mask * 0.70 + moved.astype(np.float32) * 0.30).clip(0,255).astype("uint8")
                    object_mask = Image.fromarray(cv2.GaussianBlur(refine_object_mask(mask_array, object_preset), (0,0), blur)); tracking_confidence = min(1.0, len(good_new) / 40.0)
                track_points = good_new.reshape(-1,1,2)
            else: track_points = None; tracking_confidence = 0.0
        if object_mask is not None and (track_points is None or len(track_points) < 12):
            refreshed_mask = np.asarray(object_mask, dtype=np.uint8)
            refreshed = cv2.goodFeaturesToTrack(gray, maxCorners=120, qualityLevel=0.01, minDistance=8, mask=refreshed_mask)
            if refreshed is not None:
                track_points = refreshed
                track_reacquire_count += 1
                tracking_confidence = max(tracking_confidence, min(0.8, len(refreshed) / 80.0))
        tracking_confidence_sum += tracking_confidence; camera_motion_sum += frame_camera_motion; target_motion_sum += frame_target_motion
        previous_gray = gray
        processing_rgb = analysis_rgb
        if observed_color_map is not None and frame_transform is not None and object_mask is not None:
            aligned_observed = cv2.warpAffine(observed_color_map, frame_transform, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            accumulation_strength = 0.36 if profile == "observed_color" else 0.16 if profile == "observed_conservative" else 0.12
            observed_mask = (np.asarray(object_mask, dtype=np.float32) / 255.0)[..., None] * accumulation_strength
            observed_color_map = (analysis_rgb.astype(np.float32) * (1.0 - observed_mask) + aligned_observed.astype(np.float32) * observed_mask).clip(0, 255).astype("uint8")
            observed_color_frames += 1
        else:
            observed_color_map = analysis_rgb.copy()
        if profile in {"observed_color", "observed_conservative"}:
            processing_rgb = observed_color_map
        if previous_analysis_rgb is not None and frame_transform is not None and object_mask is not None:
            aligned_source = cv2.warpAffine(previous_analysis_rgb, frame_transform, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            fusion_strength = 0.18 * min(1.0, tracking_confidence)
            fusion_mask = (np.asarray(object_mask, dtype=np.float32) / 255.0)[..., None] * fusion_strength
            if profile not in {"observed_color", "observed_conservative"}:
                processing_rgb = (analysis_rgb.astype(np.float32) * (1.0 - fusion_mask) + aligned_source.astype(np.float32) * fusion_mask).clip(0, 255).astype("uint8")
            temporal_fusion_frames += 1; temporal_fusion_weight_sum += fusion_strength
        enhanced = process_image(Image.fromarray(processing_rgb), settings)
        enhanced = Image.composite(enhanced, Image.fromarray(analysis_rgb), object_mask)
        output_array = np.asarray(enhanced.convert("RGB"))
        if previous_enhanced is not None and frame_transform is not None:
            aligned = cv2.warpAffine(previous_enhanced, frame_transform, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            mask_weight = (np.asarray(object_mask, dtype=np.float32) / 255.0)[..., None] * 0.20
            output_array = (output_array.astype(np.float32) * (1.0 - mask_weight) + aligned.astype(np.float32) * mask_weight).clip(0, 255).astype("uint8")
        previous_enhanced = output_array
        current_mask_array = np.asarray(object_mask, dtype=np.float32) / 255.0
        if count % max(1, int(fps // 5) or 1) == 0:
            skeleton_pixels, endpoints = skeleton_features(np.asarray(object_mask)); skeleton_length += skeleton_pixels; skeleton_endpoints += endpoints; skeleton_samples += 1
        if previous_mask_array is not None: temporal_shape_sum += 1.0 - float(np.mean(np.abs(current_mask_array - previous_mask_array)))
        previous_mask_array = current_mask_array
        previous_analysis_rgb = analysis_rgb
        information_gain += float(np.mean(np.abs(output_array.astype(np.float32) - analysis_rgb.astype(np.float32))))
        edge_gain += float(np.mean(cv2.Canny(cv2.cvtColor(output_array, cv2.COLOR_RGB2GRAY), 60, 150) > 0))
        components, area, elongated, holes, symmetry = shape_features(output_array); component_count += components; component_area += area; elongated_count += elongated; hole_count += holes; symmetry_sum += symmetry
        clipping += float(np.mean((output_array <= 2) | (output_array >= 253)))
        deviation += float(np.mean(np.abs(output_array.astype(np.float32) - analysis_rgb.astype(np.float32))))
        output_gray = cv2.cvtColor(output_array, cv2.COLOR_RGB2GRAY); source_gray = cv2.cvtColor(analysis_rgb, cv2.COLOR_RGB2GRAY)
        noise_sum += max(0.0, float(cv2.Laplacian(output_gray, cv2.CV_32F).var() - cv2.Laplacian(source_gray, cv2.CV_32F).var()))
        halo_sum += float(np.mean(np.abs(cv2.Laplacian(output_gray, cv2.CV_32F)))) / 255.0
        if previous_output is not None: flicker_sum += float(np.mean(np.abs(output_array.astype(np.float32) - previous_output.astype(np.float32))))
        previous_output = output_array
        writer.write(cv2.cvtColor(output_array, cv2.COLOR_RGB2BGR)); count += 1
        if count % 30 == 0:
            flicker = flicker_sum / max(1, count - 1); stability = max(0.0, 1.0 - flicker / 255.0)
            print(f"processed frames: {count} tracking_confidence={tracking_confidence:.2f} target_motion={frame_target_motion:.1f} camera_motion={frame_camera_motion:.1f} flicker={flicker:.2f} temporal_stability={stability:.3f}", flush=True)
    cap.release(); writer.release()
    avg_flicker = flicker_sum / max(1, count - 1); avg_gain = information_gain / max(1, count)
    avg_edge = edge_gain / max(1, count); avg_clip = clipping / max(1, count); avg_deviation = deviation / max(1, count)
    avg_components = component_count / max(1, count); avg_area = component_area / max(1, count); avg_elongated = elongated_count / max(1, count); avg_holes = hole_count / max(1, count); avg_symmetry = symmetry_sum / max(1, count); avg_skeleton_length = skeleton_length / max(1, skeleton_samples); avg_skeleton_endpoints = skeleton_endpoints / max(1, skeleton_samples)
    avg_noise = noise_sum / max(1, count); avg_halo = halo_sum / max(1, count); temporal_shape = temporal_shape_sum / max(1, count - 1)
    avg_tracking_confidence = tracking_confidence_sum / max(1, count); avg_camera_motion = camera_motion_sum / max(1, count); avg_target_motion = target_motion_sum / max(1, count)
    shape_score = min(20.0, avg_components * 0.15 + avg_elongated * 0.35 + avg_holes * 0.2 + avg_symmetry * 2.0 + avg_skeleton_endpoints * 0.1 + avg_area / max(1, width * height) * 5.0)
    preset_bonus = {"clothing": avg_area / max(1, width*height)*6.0, "cloth": temporal_shape*5.0, "shirt": avg_area / max(1, width*height)*6.5 + avg_symmetry*1.5, "bra": avg_area / max(1, width*height)*5.8 + avg_symmetry*2.0, "panties": avg_area / max(1, width*height)*5.8 + avg_symmetry*1.8, "skin": avg_tracking_confidence*3.0 + avg_area / max(1, width*height)*3.0, "carpet": temporal_shape*5.5 + avg_area / max(1, width*height)*3.0, "ribbon": avg_elongated*0.5, "regular": avg_components*0.1, "solid": avg_tracking_confidence*4.0, "generic": 0.0}[object_preset]
    score = avg_gain * 0.28 + avg_edge * 18.0 + shape_score + temporal_shape * 8.0 + preset_bonus + avg_tracking_confidence * 20.0 - avg_flicker * 0.45 - avg_camera_motion * 0.1 - avg_clip * 24.0 - avg_deviation * 0.04 - min(10.0, avg_noise/500.0) - avg_halo*4.0
    print(f"candidate_score={score:.2f} information_gain={avg_gain:.2f} edge_gain={avg_edge:.3f} clipping={avg_clip:.3f} flicker_penalty={avg_flicker:.2f}", flush=True)
    audio_input = ["-ss", f"{preview_start_seconds:.6f}", "-i", str(source)] if preview_start_seconds else ["-i", str(source)]
    subprocess.run(["ffmpeg", "-y", "-i", str(temp), *audio_input, "-map", "0:v:0", "-map", "1:a?", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "copy", "-shortest", str(target)], check=True)
    temp.unlink(missing_ok=True)
    return {"score": score, "mask_preview": str(mask_preview_path), "resolved_object_preset": object_preset, "surface_preset": surface_preset, "reference_preset": reference_preset, "reference_image_count": reference_image_count, "surface_reference_image_count": reference_count, "surface_reference_clusters": reference_clusters or [], "preview_start_seconds": preview_start_seconds, "surface_alpha": surface_alpha, "information_gain": avg_gain, "edge_gain": avg_edge, "shape_score": shape_score, "temporal_shape_consistency": temporal_shape, "temporal_fusion_frames": temporal_fusion_frames, "temporal_fusion_strength": temporal_fusion_weight_sum / max(1, temporal_fusion_frames), "observed_color_frames": observed_color_frames, "noise": avg_noise, "halo": avg_halo, "components": avg_components, "component_area": avg_area, "elongated_components": avg_elongated, "holes": avg_holes, "symmetry": avg_symmetry, "skeleton_length": avg_skeleton_length, "skeleton_endpoints": avg_skeleton_endpoints, "skeleton_sample_count": skeleton_samples, "clipping": avg_clip, "deviation": avg_deviation, "flicker": avg_flicker, "tracking_confidence": avg_tracking_confidence, "target_motion": avg_target_motion, "camera_motion": avg_camera_motion, "scene_change_count": scene_change_count, "mask_reinitialize_count": mask_reinitialize_count, "track_reacquire_count": track_reacquire_count}

def process_videos(source, target, profile="balanced", object_preset="generic", preview_seconds=0, roi=None, preview_start_seconds=0, reference_dir=None, surface_reference_dir=None, surface_preset="auto", denoise_reference=False):
    target.mkdir(parents=True, exist_ok=True)
    videos = [source] if source.is_file() and source.suffix.lower() in VIDEO_EXTS else sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    if not videos: raise ValueError(f"動画ファイルが見つかりません: {source}")
    scores = []
    for path in videos:
        relative = Path(path.name) if source.is_file() else path.relative_to(source)
        out = target / relative.with_name(path.stem + "_enhanced.mp4")
        metrics = process_video(path, out, profile, object_preset, preview_seconds, roi, preview_start_seconds, reference_dir, surface_reference_dir, surface_preset, denoise_reference)
        scores.append({"input": str(path), "output": str(out), "object_preset": metrics.get("resolved_object_preset", object_preset), "requested_object_preset": object_preset, "surface_preset": surface_preset, "roi": roi, "preview_seconds": preview_seconds, "preview_start_seconds": preview_start_seconds, "reference_dir": str(reference_dir or ""), "surface_reference_dir": str(surface_reference_dir or ""), **metrics})
        print(f"processed: {path}", flush=True)
    scores.sort(key=lambda item: item.get("score", float("-inf")), reverse=True)
    (target / "candidate_scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    if scores:
        (target / "best_candidate.json").write_text(json.dumps(scores[0], ensure_ascii=False, indent=2), encoding="utf-8")
        lines = ["# Candidate Ranking", "", "| Rank | Score | Preset | Tracking | Scene changes | Output |", "|---:|---:|---|---:|---:|---|"] + [f"| {index} | {item['score']:.2f} | {item['object_preset']} | {item.get('tracking_confidence', 0):.2f} | {item.get('scene_change_count', 0)} | {item['output']} |" for index, item in enumerate(scores, 1)]
        (target / "candidate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return scores

def write_candidate_comparison(entries, output):
    import cv2
    selected = entries[:12]
    tiles = []
    for index, item in enumerate(selected, 1):
        capture = cv2.VideoCapture(item["output"])
        ok, frame = capture.read(); capture.release()
        if not ok:
            continue
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image.thumbnail((300, 180))
        tile = Image.new("RGB", (320, 230), "#202020")
        tile.paste(image, ((320 - image.width) // 2, 8))
        label = f"{index}. {item['profile']}  score {item['score']:.2f}"
        ImageDraw.Draw(tile).text((8, 194), label, fill="white")
        tiles.append(tile)
    if not tiles:
        return None
    columns = 3; rows = (len(tiles) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 320, rows * 230), "#101010")
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % columns) * 320, (index // columns) * 230))
    path = output / "candidate_comparison.png"
    sheet.save(path)
    return path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("image", "video"), default="")
    parser.add_argument("--input", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--profile", choices=("color", "color_strong", "shape", "shape_strong", "balanced", "balanced_strong", "conservative", "observed_color", "observed_conservative", "all"), default="balanced")
    parser.add_argument("--object-preset", choices=tuple(OBJECT_PRESETS), default="generic")
    parser.add_argument("--preview-seconds", type=float, default=0, help="0なら全尺。正数なら先頭からその秒数だけ候補生成")
    parser.add_argument("--preview-start-seconds", type=float, default=0, help="候補プレビューを開始する秒数。全尺処理では0を指定")
    parser.add_argument("--reference-dir", default="", help="形状ヒントに使う参考画像フォルダ")
    parser.add_argument("--surface-reference-dir", default="", help="透過表面の色推定に使う参考画像フォルダ")
    parser.add_argument("--surface-preset", choices=tuple(SURFACE_PRESETS), default="auto")
    parser.add_argument("--roi", default="", help="対象範囲を正規化座標 x,y,width,height で指定")
    parser.add_argument("--analyze-reference", action="store_true", help="対象参考画像の形状からプリセット候補だけをJSONで出力する")
    parser.add_argument("--denoise-reference", action="store_true", help="参考画像の形状・表面色推定前にノイズを抑える")
    args = parser.parse_args()
    roi = tuple(float(value) for value in args.roi.split(",")) if args.roi else None
    reference_dir = Path(args.reference_dir) if args.reference_dir else None
    surface_reference_dir = Path(args.surface_reference_dir) if args.surface_reference_dir else None
    if reference_dir is not None and not reference_dir.is_dir():
        raise ValueError(f"参考画像フォルダが見つかりません: {reference_dir}")
    if surface_reference_dir is not None and not surface_reference_dir.is_dir():
        raise ValueError(f"表面参考画像フォルダが見つかりません: {surface_reference_dir}")
    if args.analyze_reference:
        if reference_dir is None:
            raise ValueError("--analyze-reference には --reference-dir が必要です")
        print(json.dumps(reference_shape_summary(reference_dir, args.denoise_reference), ensure_ascii=False), flush=True)
        return
    if not args.mode or not args.input or not args.output:
        raise ValueError("通常処理には --mode、--input、--output が必要です")
    if roi is not None and (len(roi) != 4 or any(value < 0 or value > 1 for value in roi) or roi[2] <= 0 or roi[3] <= 0 or roi[0] + roi[2] > 1 or roi[1] + roi[3] > 1):
        raise ValueError("--roi は 0〜1 の x,y,width,height を指定してください")
    if args.profile == "all":
        combined = []
        for profile in ("color", "color_strong", "shape", "shape_strong", "balanced", "balanced_strong", "conservative", "observed_color", "observed_conservative"):
            target = Path(args.output) / profile
            if args.mode == "image": process_images(Path(args.input), target, profile, args.object_preset, reference_dir, surface_reference_dir, args.surface_preset, args.denoise_reference)
            else:
                for item in process_videos(Path(args.input), target, profile, args.object_preset, args.preview_seconds, roi, args.preview_start_seconds, reference_dir, surface_reference_dir, args.surface_preset, args.denoise_reference):
                    combined.append({"profile": profile, **item})
        if combined:
            combined.sort(key=lambda item: item["score"], reverse=True)
            root = Path(args.output)
            (root / "candidate_ranking.json").write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
            (root / "best_candidate.json").write_text(json.dumps(combined[0], ensure_ascii=False, indent=2), encoding="utf-8")
            lines = ["# Candidate Ranking", "", "| Rank | Profile | Score | Preset | Tracking | Scene changes | Output |", "|---:|---|---:|---|---:|---:|---|"] + [f"| {index} | {item['profile']} | {item['score']:.2f} | {item.get('object_preset', 'generic')} | {item.get('tracking_confidence', 0):.2f} | {item.get('scene_change_count', 0)} | {item['output']} |" for index, item in enumerate(combined, 1)]
            (root / "candidate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            comparison = write_candidate_comparison(combined, root)
            if comparison: print(f"candidate_comparison={comparison}", flush=True)
            print(f"best_candidate={combined[0]['profile']} score={combined[0]['score']:.2f}", flush=True)
    elif args.mode == "image": process_images(Path(args.input), Path(args.output), args.profile, args.object_preset, reference_dir, surface_reference_dir, args.surface_preset, args.denoise_reference)
    else:
        source, target = Path(args.input), Path(args.output)
        process_videos(source, target, args.profile, args.object_preset, args.preview_seconds, roi, args.preview_start_seconds, reference_dir, surface_reference_dir, args.surface_preset, args.denoise_reference) if source.is_dir() else process_video(source, target, args.profile, args.object_preset, args.preview_seconds, roi, args.preview_start_seconds, reference_dir, surface_reference_dir, args.surface_preset, args.denoise_reference)

if __name__ == "__main__": main()
