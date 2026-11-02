"""Animated plan preview rendering using the project's Pillow dependency."""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw

from .contracts import CameraKey, CameraPlan

PREVIEW_SIZE = (480, 270)
MAX_PREVIEW_FRAMES = 48


# {
# 責務: [render_camera_preview: camera planからanimated GIF previewを作る]
# 処理: [frameをsampleしsubject/cameraをtop-down storyboardとして描画する]
# 引数: [plan: validated camera plan]
# 戻り値: [bytes: animated GIF]
# }
def render_camera_preview(plan: CameraPlan) -> bytes:
    if not plan.keys:
        raise ValueError("cannot render a camera preview without keys")
    sampled = _sample_keys(plan.keys)
    positions = [key.position for key in plan.keys]
    x_values = [position[0] for position in positions]
    z_values = [position[2] for position in positions]
    x_min, x_max = min(x_values), max(x_values)
    z_min, z_max = min(z_values), max(z_values)
    image_frames = []
    for current in sampled:
        image = Image.new("RGB", PREVIEW_SIZE, "#171923")
        draw = ImageDraw.Draw(image)
        margin = 36
        draw.text((margin, 12), f"{plan.style.value} · frame {current.frame}", fill="#f5f7fa")
        plot_width = PREVIEW_SIZE[0] - margin * 2
        plot_height = PREVIEW_SIZE[1] - margin * 2
        draw.rectangle(
            (margin, margin, margin + plot_width, margin + plot_height), outline="#667085"
        )
        points = [
            _map_position(position, x_min, x_max, z_min, z_max, margin, plot_width, plot_height)
            for position in positions
        ]
        if len(points) > 1:
            draw.line(points, fill="#85d7ff", width=2)
        target = _map_position(
            current.position, x_min, x_max, z_min, z_max, margin, plot_width, plot_height
        )
        camera = _camera_marker(current, target)
        draw.line((camera, target), fill="#ffd166", width=2)
        draw.polygon(_triangle(camera, current.rotation[1]), fill="#ffd166")
        draw.ellipse((target[0] - 6, target[1] - 6, target[0] + 6, target[1] + 6), fill="#ff6b6b")
        draw.text(
            (margin, PREVIEW_SIZE[1] - 22),
            f"distance {current.distance:.1f} · FOV {current.field_of_view}°",
            fill="#d0d5dd",
        )
        image_frames.append(image)
    output = io.BytesIO()
    image_frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=image_frames[1:],
        duration=120,
        loop=0,
        optimize=False,
    )
    return output.getvalue()


# {
# 責務: [_sample_keys: preview GIF用にcamera keysを間引く]
# 処理: [全keyを表示可能数へ均等sampleする]
# 引数: [keys: camera keyframes]
# 戻り値: [tuple[CameraKey, ...]: sampled keys]
# }
def _sample_keys(keys: tuple[CameraKey, ...]) -> tuple[CameraKey, ...]:
    if len(keys) <= MAX_PREVIEW_FRAMES:
        return keys
    indexes = sorted(
        {
            round(index * (len(keys) - 1) / (MAX_PREVIEW_FRAMES - 1))
            for index in range(MAX_PREVIEW_FRAMES)
        }
    )
    return tuple(keys[index] for index in indexes)


# {
# 責務: [_map_position: stage positionをpreview座標へ変換する]
# 処理: [x/z範囲をplotへscaleし中心位置を返す]
# 引数: [position, ranges, viewport: normalized drawing inputs]
# 戻り値: [tuple[int, int]: image point]
# }
def _map_position(position, x_min, x_max, z_min, z_max, margin, width, height):
    x_ratio = 0.5 if x_max == x_min else (position[0] - x_min) / (x_max - x_min)
    z_ratio = 0.5 if z_max == z_min else (position[2] - z_min) / (z_max - z_min)
    return margin + round(x_ratio * width), margin + round((1.0 - z_ratio) * height)


# {
# 責務: [_camera_marker: camera位置をtargetとdistanceから近似する]
# 処理: [camera yawをtop-down viewの距離offsetに変換する]
# 引数: [key, target: camera keyとtarget point]
# 戻り値: [tuple[int, int]: camera marker point]
# }
def _camera_marker(key: CameraKey, target: tuple[int, int]) -> tuple[int, int]:
    yaw = key.rotation[1]
    radius = min(42.0, max(12.0, key.distance * 1.5))
    return round(target[0] + math.sin(yaw) * radius), round(target[1] - math.cos(yaw) * radius)


# {
# 責務: [_triangle: direction marker polygonを構築する]
# 処理: [yawに沿った三角形頂点を返す]
# 引数: [center, yaw: marker centerとcamera yaw]
# 戻り値: [tuple[tuple[int, int], ...]: triangle points]
# }
def _triangle(center: tuple[int, int], yaw: float) -> tuple[tuple[int, int], ...]:
    tip = (round(center[0] + math.sin(yaw) * 9), round(center[1] - math.cos(yaw) * 9))
    left = (round(center[0] - 5), round(center[1] + 5))
    right = (round(center[0] + 5), round(center[1] + 5))
    return tip, left, right
