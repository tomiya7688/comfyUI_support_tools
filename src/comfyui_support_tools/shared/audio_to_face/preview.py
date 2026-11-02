"""Small animated face preview rendered from generated morph curves."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw

from .contracts import MorphKey

PREVIEW_SIZE = (320, 240)


# {
# 責務: [render_face_preview: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [keys, end_frame: 処理入力]
# 戻り値: [bytes: 処理結果]
# }
def render_face_preview(keys: tuple[MorphKey, ...], end_frame: int) -> bytes:
    sample_frames = tuple(range(0, max(end_frame, 1) + 1, max(1, end_frame // 48)))[:48]
    frames = []
    for frame in sample_frames:
        weights = _sample_morphs(keys, frame)
        image = Image.new("RGB", PREVIEW_SIZE, "#202333")
        draw = ImageDraw.Draw(image)
        draw.ellipse((70, 20, 250, 220), fill="#ffe0c2", outline="#493c50", width=4)
        blink = weights.get("まばたき", 0.0)
        eye_height = max(2, round(18 * (1.0 - blink)))
        draw.ellipse((112, 88, 142, 88 + eye_height), fill="#253452")
        draw.ellipse((178, 88, 208, 88 + eye_height), fill="#253452")
        openness = max(
            (weights.get(name, 0.0) for name in ("あ", "い", "う", "え", "お")), default=0.0
        )
        mouth_width = 16 + round(openness * 18)
        mouth_height = 3 + round(openness * 28)
        draw.ellipse(
            (160 - mouth_width, 155 - mouth_height, 160 + mouth_width, 155 + mouth_height),
            fill="#a1284b",
        )
        draw.text((12, 10), f"frame {frame}", fill="white")
        frames.append(image)
    output = io.BytesIO()
    frames[0].save(
        output, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0
    )
    return output.getvalue()


# {
# 責務: [_sample_morphs: audio-to-face処理を実行する]
# 処理: [入力を検証し、再現可能なfacial motion結果を返す]
# 引数: [keys, frame: 処理入力]
# 戻り値: [dict[str, float]: 処理結果]
# }
def _sample_morphs(keys: tuple[MorphKey, ...], frame: int) -> dict[str, float]:
    result = {}
    for key in keys:
        if key.frame <= frame:
            result[key.name] = key.weight
    return result
