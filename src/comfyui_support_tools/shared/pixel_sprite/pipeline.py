"""Canonical-anchored sprite frame generation, pixel normalization and sheet packing."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from PIL import Image

from .contracts import (
    SpriteAnimationResult,
    SpriteDirection,
    SpriteFrame,
    SpriteFrameGenerator,
    SpriteFrameOrder,
    SpriteFrameSpec,
    SpriteSequenceRequest,
)


# {
# 責務: [SpriteSequenceService: pixel sprite pipelineのdomain責務を提供する]
# フィールド: [sequence contractまたはservice dependencies]
# 処理: [canonical anchorから安全なsprite assetsを構成する]
# }
class SpriteSequenceService:
    """Generate a bounded frame sequence and export reproducible game assets."""

    # {
    # 責務: [__init__: pixel sprite assetsの処理または検証を行う]
    # 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
    # 引数: [self, generator, evaluator]
    # 戻り値: [sprite処理結果]
    # }
    def __init__(
        self, generator: SpriteFrameGenerator | None = None, evaluator: object | None = None
    ) -> None:
        self.generator = generator
        self.evaluator = evaluator

    # {
    # 責務: [create: pixel sprite assetsの処理または検証を行う]
    # 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
    # 引数: [self, request]
    # 戻り値: [sprite処理結果]
    # }
    def create(self, request: SpriteSequenceRequest) -> SpriteAnimationResult:
        output = Path(request.output_directory).expanduser().resolve()
        if not request.output_directory:
            raise ValueError("output_directory is required")
        if output.exists():
            raise FileExistsError(f"refusing to overwrite sprite output directory: {output}")
        specs = make_frame_specs(request)
        generated_frames: list[SpriteFrame] = []
        for spec in specs:
            canonical_idle = (
                spec.action == "idle"
                and spec.direction is SpriteDirection.FRONT
                and spec.index == 0
            )
            if canonical_idle:
                generated = request.canonical.copy()
            elif self.generator is None:
                raise RuntimeError("a frame generator is required for non-canonical sprite poses")
            else:
                generated = self.generator.generate(request.canonical.copy(), spec, request.prompt)
            if not isinstance(generated, Image.Image):
                raise TypeError(
                    f"generator returned no image for {spec.action}/{spec.direction.value}/{spec.index}"
                )
            generated_frames.append(SpriteFrame(spec, generated))
        return self._finalize(request, tuple(generated_frames))

    # {
    # 責務: [repack: pixel sprite assetsの処理または検証を行う]
    # 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
    # 引数: [self, request, frames]
    # 戻り値: [sprite処理結果]
    # }
    def repack(
        self, request: SpriteSequenceRequest, frames: tuple[SpriteFrame, ...]
    ) -> SpriteAnimationResult:
        """Re-grid and repack externally edited frames through the same palette anchor."""
        expected = len(request.directions) * len(request.actions) * request.frames_per_action
        if len(frames) != expected:
            raise ValueError(f"expected {expected} edited frames, got {len(frames)}")
        expected_keys = {_frame_key(spec) for spec in make_frame_specs(request)}
        actual_keys = {_frame_key(frame.spec) for frame in frames}
        if actual_keys != expected_keys or len(actual_keys) != len(frames):
            raise ValueError(
                "edited frame specs must exactly match the requested action/direction sequence"
            )
        return self._finalize(request, frames)

    # {
    # 責務: [_finalize: pixel sprite assetsの処理または検証を行う]
    # 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
    # 引数: [self, request, source_frames]
    # 戻り値: [sprite処理結果]
    # }
    def _finalize(
        self, request: SpriteSequenceRequest, source_frames: tuple[SpriteFrame, ...]
    ) -> SpriteAnimationResult:
        canonical = normalize_to_cell(request.canonical, request.cell_width, request.cell_height)
        palette = _palette_anchor(request.canonical, request.palette_colors)
        frames: list[SpriteFrame] = []
        for frame in source_frames:
            normalized = normalize_to_cell(frame.image, request.cell_width, request.cell_height)
            quantized = apply_shared_palette(normalized, palette)
            metrics, warnings = self._evaluate(canonical, quantized, frame.spec)
            frames.append(SpriteFrame(frame.spec, quantized, **metrics, warnings=warnings))
        ordered = order_frames(tuple(frames), request.frame_order)
        columns, rows = resolve_layout(len(ordered), request.columns, request.rows)
        sheet, coordinates = pack_sheet(ordered, request, columns, rows)
        warnings = tuple(dict.fromkeys(warning for frame in ordered for warning in frame.warnings))
        return export_sequence(
            request,
            ordered,
            sheet,
            coordinates,
            columns,
            rows,
            palette,
            warnings,
        )

    # {
    # 責務: [_evaluate: pixel sprite assetsの処理または検証を行う]
    # 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
    # 引数: [self, canonical, frame, spec]
    # 戻り値: [sprite処理結果]
    # }
    def _evaluate(
        self, canonical: Image.Image, frame: Image.Image, spec: SpriteFrameSpec
    ) -> tuple[dict[str, float | None], tuple[str, ...]]:
        if self.evaluator is None:
            return (
                {"identity_score": None, "shape_score": None, "palette_score": 1.0},
                ("No identity/shape evaluator configured; inspect frame consistency manually.",),
            )
        evaluate = getattr(self.evaluator, "evaluate", None)
        if not callable(evaluate):
            raise TypeError("evaluator must provide evaluate(canonical, frame, spec)")
        values = evaluate(canonical, frame, spec)
        if not isinstance(values, dict):
            raise TypeError("sprite evaluator must return a score mapping")
        result: dict[str, float | None] = {}
        warnings: list[str] = []
        for key in ("identity", "shape", "palette"):
            score = values.get(key)
            if score is None:
                result[f"{key}_score"] = None
                continue
            if (
                not isinstance(score, (float, int))
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                raise ValueError(f"evaluator {key} score must be finite and between 0 and 1")
            result[f"{key}_score"] = float(score)
            if score < 0.5:
                warnings.append(
                    f"Low {key} consistency score ({score:.2f}) for {spec.action}/{spec.direction.value}/{spec.index}."
                )
        if result["identity_score"] is None:
            warnings.append("Identity similarity was not measured by the configured evaluator.")
        return result, tuple(warnings)


# {
# 責務: [make_frame_specs: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [request]
# 戻り値: [sprite処理結果]
# }
def make_frame_specs(request: SpriteSequenceRequest) -> tuple[SpriteFrameSpec, ...]:
    pose_lookup = {
        (action, direction, index): instruction
        for action, direction, index, instruction in request.pose_instructions
    }
    specs = []
    for action in request.actions:
        for direction in request.directions:
            for index in range(request.frames_per_action):
                phase = index / request.frames_per_action
                instruction = pose_lookup.get((action, direction.value, index), "")
                specs.append(
                    SpriteFrameSpec(
                        action, direction, index, request.frames_per_action, phase, instruction
                    )
                )
    return tuple(specs)


# {
# 責務: [normalize_to_cell: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [image, width, height]
# 戻り値: [sprite処理結果]
# }
def normalize_to_cell(image: Image.Image, width: int, height: int) -> Image.Image:
    source = image.convert("RGBA")
    scale = min(width / source.width, height / source.height)
    resized = source.resize(
        (max(1, round(source.width * scale)), max(1, round(source.height * scale))),
        Image.Resampling.NEAREST,
    )
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return canvas


# {
# 責務: [_palette_anchor: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [canonical, colors]
# 戻り値: [sprite処理結果]
# }
def _palette_anchor(canonical: Image.Image, colors: int) -> Image.Image:
    return canonical.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT)


# {
# 責務: [apply_shared_palette: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [image, palette]
# 戻り値: [sprite処理結果]
# }
def apply_shared_palette(image: Image.Image, palette: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    quantized = (
        rgba.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB")
    )
    quantized.putalpha(alpha)
    return quantized


# {
# 責務: [order_frames: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [frames, order]
# 戻り値: [sprite処理結果]
# }
def order_frames(
    frames: tuple[SpriteFrame, ...], order: SpriteFrameOrder
) -> tuple[SpriteFrame, ...]:
    direction_order = {direction.value: index for index, direction in enumerate(SpriteDirection)}
    action_order = {frame.spec.action: index for index, frame in enumerate(frames)}

    # {
    # 責務: [frame_key: frame metadataからlayout order sort keyを得る]
    # 処理: [order enumに応じdirection/action/indexの優先度を変える]
    # 引数: [frame: sorted対象sprite frame]
    # 戻り値: [tuple: stable frame sort key]
    # }
    def frame_key(frame: SpriteFrame) -> tuple[int, ...]:
        direction_index = direction_order[frame.spec.direction.value]
        action_index = action_order[frame.spec.action]
        if order is SpriteFrameOrder.DIRECTION_MAJOR:
            return direction_index, action_index, frame.spec.index
        if order is SpriteFrameOrder.ACTION_MAJOR:
            return action_index, direction_index, frame.spec.index
        return frame.spec.index, action_index, direction_index

    return tuple(sorted(frames, key=frame_key))


# {
# 責務: [resolve_layout: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [count, columns, rows]
# 戻り値: [sprite処理結果]
# }
def resolve_layout(count: int, columns: int, rows: int) -> tuple[int, int]:
    if columns and rows:
        if columns * rows < count:
            raise ValueError("sprite sheet layout does not fit all frames")
        return columns, rows
    if columns:
        return columns, math.ceil(count / columns)
    if rows:
        return math.ceil(count / rows), rows
    columns = math.ceil(math.sqrt(count))
    return columns, math.ceil(count / columns)


# {
# 責務: [pack_sheet: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [frames, request, columns, rows]
# 戻り値: [sprite処理結果]
# }
def pack_sheet(
    frames: tuple[SpriteFrame, ...],
    request: SpriteSequenceRequest,
    columns: int,
    rows: int,
) -> tuple[Image.Image, dict[str, tuple[int, int, int, int]]]:
    width = (
        request.margin * 2 + columns * request.cell_width + max(0, columns - 1) * request.padding
    )
    height = request.margin * 2 + rows * request.cell_height + max(0, rows - 1) * request.padding
    if width > 8192 or height > 8192 or width * height > 64_000_000:
        raise ValueError("packed sprite sheet exceeds 8192px edge or 64 megapixel safety limit")
    sheet = Image.new("RGBA", (width, height), request.background)
    coordinates: dict[str, tuple[int, int, int, int]] = {}
    for slot, frame in enumerate(frames):
        column, row = slot % columns, slot // columns
        x = request.margin + column * (request.cell_width + request.padding)
        y = request.margin + row * (request.cell_height + request.padding)
        sheet.alpha_composite(frame.image, (x, y))
        coordinates[_frame_key(frame.spec)] = (x, y, request.cell_width, request.cell_height)
    return sheet, coordinates


# {
# 責務: [export_sequence: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [request, frames, sheet, coordinates, columns, rows, palette, warnings]
# 戻り値: [sprite処理結果]
# }
def export_sequence(
    request: SpriteSequenceRequest,
    frames: tuple[SpriteFrame, ...],
    sheet: Image.Image,
    coordinates: dict[str, tuple[int, int, int, int]],
    columns: int,
    rows: int,
    palette: Image.Image,
    warnings: tuple[str, ...],
) -> SpriteAnimationResult:
    output = Path(request.output_directory).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        sheet.save(stage / "sprite_sheet.png", format="PNG", optimize=True)
        frames_path = stage / "frames"
        frames_path.mkdir()
        for frame in frames:
            frame.image.save(
                frames_path / f"{_frame_filename(frame.spec)}.png", format="PNG", optimize=True
            )
        gif_name = "animation.gif" if request.export_gif else None
        webp_name = "animation.webp" if request.export_webp else None
        if gif_name:
            _save_gif(frames, stage / gif_name, request.fps)
        if webp_name:
            _save_webp(frames, stage / webp_name, request.fps)
        meta = {
            "format_version": 1,
            "prompt": request.prompt,
            "canonical_sha256": hashlib.sha256(
                request.canonical.convert("RGBA").tobytes()
            ).hexdigest(),
            "cell": {"width": request.cell_width, "height": request.cell_height},
            "layout": {
                "columns": columns,
                "rows": rows,
                "margin": request.margin,
                "padding": request.padding,
                "order": request.frame_order.value,
                "sheet": "sprite_sheet.png",
            },
            "palette": {
                "colors": request.palette_colors,
                "rgb": _palette_colors(palette),
                "source": "canonical_sprite",
            },
            "fps": request.fps,
            "frames": [
                {
                    "file": f"frames/{_frame_filename(frame.spec)}.png",
                    "action": frame.spec.action,
                    "direction": frame.spec.direction.value,
                    "index": frame.spec.index,
                    "phase": frame.spec.phase,
                    "pose_instruction": frame.spec.pose_instruction,
                    "rect": list(coordinates[_frame_key(frame.spec)]),
                    "scores": {
                        "identity": frame.identity_score,
                        "shape": frame.shape_score,
                        "palette": frame.palette_score,
                    },
                    "warnings": list(frame.warnings),
                }
                for frame in frames
            ],
            "warnings": list(warnings),
        }
        metadata = stage / "animation.json"
        metadata.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if output.exists():
            raise FileExistsError(f"refusing to overwrite sprite output directory: {output}")
        os.replace(stage, output)
    except Exception:
        if stage.exists():
            import shutil

            shutil.rmtree(stage, ignore_errors=True)
        raise
    return SpriteAnimationResult(
        str(output / "sprite_sheet.png"),
        str(output / "frames"),
        str(output / "animation.json"),
        str(output / gif_name) if gif_name else None,
        str(output / webp_name) if webp_name else None,
        len(frames),
        columns,
        rows,
        frames,
        warnings,
    )


# {
# 責務: [_save_gif: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [frames, path, fps]
# 戻り値: [sprite処理結果]
# }
def _save_gif(frames: tuple[SpriteFrame, ...], path: Path, fps: int) -> None:
    images = [frame.image.convert("RGBA") for frame in frames]
    images[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=1000 // fps,
        loop=0,
        disposal=2,
        optimize=False,
    )


# {
# 責務: [_save_webp: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [frames, path, fps]
# 戻り値: [sprite処理結果]
# }
def _save_webp(frames: tuple[SpriteFrame, ...], path: Path, fps: int) -> None:
    images = [frame.image.convert("RGBA") for frame in frames]
    images[0].save(
        path,
        format="WEBP",
        save_all=True,
        append_images=images[1:],
        duration=1000 // fps,
        loop=0,
        lossless=True,
        method=6,
    )


# {
# 責務: [_palette_colors: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [palette]
# 戻り値: [sprite処理結果]
# }
def _palette_colors(palette: Image.Image) -> list[list[int]]:
    values = palette.getpalette() or []
    used = palette.getcolors(maxcolors=256) or []
    indices = sorted(index for _count, index in used)
    return [values[index * 3 : index * 3 + 3] for index in indices if index * 3 + 2 < len(values)]


# {
# 責務: [_frame_key: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [spec]
# 戻り値: [sprite処理結果]
# }
def _frame_key(spec: SpriteFrameSpec) -> str:
    return f"{spec.action}:{spec.direction.value}:{spec.index}"


# {
# 責務: [_frame_filename: pixel sprite assetsの処理または検証を行う]
# 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
# 引数: [spec]
# 戻り値: [sprite処理結果]
# }
def _frame_filename(spec: SpriteFrameSpec) -> str:
    safe_action = "".join(char if char.isalnum() or char in "-_" else "_" for char in spec.action)
    return f"{safe_action}_{spec.direction.value}_{spec.index:03d}"
