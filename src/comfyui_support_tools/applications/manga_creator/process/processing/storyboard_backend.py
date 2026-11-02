"""Offline rough panel renderer for name/storyboard-stage review."""

from __future__ import annotations

import io
import random

from PIL import Image, ImageDraw, ImageFont

from comfyui_support_tools.shared.contracts.manga_creator import (
    MangaStyleMode,
    PanelRenderRequest,
    PanelRenderResult,
)


# {
# 責務: [StoryboardRenderBackend: create rough editable storyboard panel images]
# フィールド: [no mutable state]
# 処理: [render a deterministic low-detail panel proof without pretending to be a trained image model]
# }
class StoryboardRenderBackend:
    # {
    # 責務: [render_panel: render a rough composition proof for one panel]
    # 処理: [draw a scene, participant silhouettes, camera note, and narrative beat]
    # 引数: [request: panel intent and project context]
    # 戻り値: [PanelRenderResult: PNG proof with an explicit storyboard marker]
    # }
    def render_panel(self, request: PanelRenderRequest) -> PanelRenderResult:
        aspect = max(0.2, min(5.0, request.panel.bbox[2] * (0.73 / request.panel.bbox[3])))
        width, height = (
            (720, max(160, round(720 / aspect)))
            if aspect >= 1
            else (max(160, round(720 * aspect)), 720)
        )
        paper = "#fbfbfb" if request.project.style != MangaStyleMode.COLOR else "#f8f4ec"
        image = Image.new("RGB", (width, height), paper)
        draw = ImageDraw.Draw(image)
        rng = random.Random(
            request.seed
            if request.seed is not None
            else f"{request.panel.id}:{request.panel.action}"
        )
        horizon = int(height * rng.uniform(0.42, 0.67))
        draw.line((0, horizon, width, horizon), fill="#a0a0a0", width=max(1, width // 360))
        for index in range(4):
            x = int((index + 0.5) * width / 4)
            roof = horizon - rng.randint(35, 130)
            draw.rectangle((x - 35, roof, x + 35, horizon), outline="#b0b0b0", width=2)
            draw.line((x - 35, roof, x, roof - 20, x + 35, roof), fill="#b0b0b0", width=2)
        characters = [
            item for item in request.project.characters if item.id in request.panel.character_ids
        ]
        positions = dict(request.panel.character_positions)
        for index, character in enumerate(characters[:3]):
            box = positions.get(character.id)
            panel_x, panel_y, panel_width, panel_height = request.panel.bbox
            center_x = (
                int(((box[0] - panel_x) / panel_width + box[2] / panel_width / 2) * width)
                if box
                else int(width * (0.32 + index * 0.34))
            )
            center_y = (
                int(((box[1] - panel_y) / panel_height + box[3] / panel_height * 0.25) * height)
                if box
                else int(height * 0.48)
            )
            scale = max(22, min(width, height) // 12)
            draw.ellipse(
                (center_x - scale, center_y - scale, center_x + scale, center_y + scale),
                outline="#222222",
                width=3,
            )
            shoulder_y = center_y + scale * 2
            draw.line(
                (center_x, center_y + scale, center_x, shoulder_y + scale * 2),
                fill="#222222",
                width=4,
            )
            pose_offset = rng.randint(-scale, scale)
            draw.line(
                (center_x, shoulder_y, center_x - scale * 2, shoulder_y + scale + pose_offset),
                fill="#222222",
                width=3,
            )
            draw.line(
                (center_x, shoulder_y, center_x + scale * 2, shoulder_y + scale - pose_offset),
                fill="#222222",
                width=3,
            )
            draw.line(
                (center_x, shoulder_y + scale * 2, center_x - scale, shoulder_y + scale * 4),
                fill="#222222",
                width=3,
            )
            draw.line(
                (center_x, shoulder_y + scale * 2, center_x + scale, shoulder_y + scale * 4),
                fill="#222222",
                width=3,
            )
        font = ImageFont.load_default()
        label = f"STORYBOARD • {request.panel.beat or request.panel.narrative_purpose}"
        draw.rectangle((8, 8, width - 8, 38), fill="white", outline="#999999")
        draw.text((16, 15), label[:80], font=font, fill="#333333")
        caption = request.panel.action.strip().replace("\n", " ")
        if caption:
            draw.text((12, height - 28), caption[:100], font=font, fill="#555555")
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        warning = (
            "Offline storyboard sketch only; this is not final manga artwork or model inference."
        )
        return PanelRenderResult(
            output.getvalue(), "offline_storyboard_v1", request.seed, (warning,)
        )
