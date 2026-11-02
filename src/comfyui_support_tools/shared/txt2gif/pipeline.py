"""Canonical-art motion rendering, periodic loop closure, and bounded GIF encoding."""

from __future__ import annotations

import io
import math
import os
import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageChops

from .contracts import AnimationFrameBackend, DitherMode, Txt2GifRequest, Txt2GifResult


# {
#   責務: [render_key_art_loop: one canonical anime stillからregion motionのみを周期renderする]
#   処理: [static clean plateを維持し, RGBA cutoutだけをperiodic displacementでoverlayする]
#   引数: [clean_plate_png: inpainted still background, layers: localized motion regions, request: frame cadence/canvas]
#   戻り値: [tuple[Image.Image, ...]: exact-seam loop frames]
#   エラー: [ValueError: invalid image sizes or no motion layers]
# }
def render_key_art_loop(
    clean_plate_png: bytes,
    layers,
    request: Txt2GifRequest,
) -> tuple[Image.Image, ...]:
    if not layers:
        raise ValueError("key-art animation requires at least one extracted motion layer")
    with Image.open(io.BytesIO(clean_plate_png)) as source:
        clean_plate = source.convert("RGBA")
    if clean_plate.size != (request.width, request.height):
        raise ValueError("clean plate size must match the requested canvas")
    decoded_layers = []
    for layer in layers:
        with Image.open(io.BytesIO(layer.rgba_png)) as image:
            cutout = image.convert("RGBA")
        if cutout.size != clean_plate.size:
            raise ValueError(f"motion layer {layer.name!r} does not match the clean plate canvas")
        if (
            abs(layer.amplitude_x) >= clean_plate.width / 2
            or abs(layer.amplitude_y) >= clean_plate.height / 2
        ):
            raise ValueError(
                f"motion layer {layer.name!r} displacement is too large for the canvas"
            )
        decoded_layers.append((layer, cutout))

    frames = []
    period = request.frame_count - 1
    for frame_index in range(request.frame_count):
        time = frame_index / period
        frame = clean_plate.copy()
        for layer, cutout in decoded_layers:
            phase = 2 * math.pi * time + layer.phase
            offset_x = round(layer.amplitude_x * math.sin(phase))
            offset_y = round(layer.amplitude_y * math.sin(phase))
            moved = ImageChops.offset(cutout, offset_x, offset_y)
            frame.alpha_composite(moved)
        frames.append(frame)
    frames[-1] = frames[0].copy()
    return tuple(frames)


# {
#   責務: [seal_loop: arbitrary backend frame sequenceのlast frameをfirstへ一致させる]
#   処理: [RGBAをnormalizeしてfirst/lastをpixel-identicalにしloop seamを閉じる]
#   引数: [frames: ordered backend output frames]
#   戻り値: [tuple[Image.Image, ...]: seamless cyclic frame sequence]
#   エラー: [ValueError: fewer than two differently sized frames]
# }
def seal_loop(frames: tuple[Image.Image, ...]) -> tuple[Image.Image, ...]:
    if len(frames) < 2:
        raise ValueError("loop animation requires at least two frames")
    size = frames[0].size
    if any(frame.size != size for frame in frames):
        raise ValueError("animation frames must share one canvas size")
    result = tuple(frame.convert("RGBA") for frame in frames)
    return (*result[:-1], result[0].copy())


# {
#   責務: [encode_gif: shared palette/dither/size budget settingsでatomic GIF outputを作る]
#   処理: [global paletteを全frameから作成し, file budget超過時にcolor/dimensionを段階縮小する]
#   引数: [frames: closed RGBA frame sequence, request: GIF timing/quality/destination limits]
#   戻り値: [Txt2GifResult: saved GIF and measured output diagnostics]
#   エラー: [ValueError: palette/file budget cannot be satisfied, OSError: output write failure]
# }
def encode_gif(frames: tuple[Image.Image, ...], request: Txt2GifRequest) -> Txt2GifResult:
    sealed = seal_loop(frames)
    output_path = Path(request.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scale = 1.0
    colors = request.color_count
    last_size = 0
    while True:
        width = max(request.minimum_dimension, round(request.width * scale))
        height = max(request.minimum_dimension, round(request.height * scale))
        resized = tuple(
            frame.resize((width, height), Image.Resampling.LANCZOS)
            if frame.size != (width, height)
            else frame.copy()
            for frame in sealed
        )
        indexed = _apply_global_palette(resized, colors, request)
        encoded = io.BytesIO()
        indexed[0].save(
            encoded,
            format="GIF",
            save_all=True,
            append_images=list(indexed[1:]),
            duration=round(1000 / request.fps),
            loop=0,
            disposal=2,
            optimize=True,
            transparency=255,
        )
        payload = encoded.getvalue()
        last_size = len(payload)
        if last_size <= request.maximum_file_bytes:
            _atomic_write(output_path, payload)
            seam = _frame_error(indexed[0], indexed[-1])
            used_colors = len(
                {value for frame in indexed for value in frame.getdata() if value != 255}
            )
            return Txt2GifResult(
                output_path,
                len(indexed),
                request.fps,
                min(used_colors, colors),
                last_size,
                seam,
                width,
                height,
            )
        if colors > 16:
            colors = max(16, colors - 16)
        elif min(width, height) > request.minimum_dimension:
            scale *= 0.9
        else:
            raise ValueError(
                f"GIF size budget cannot be met at minimum dimensions and palette ({last_size} bytes)"
            )


# {
#   責務: [_apply_global_palette: all framesを一つのpaletteへquantizeする]
#   処理: [bounded thumbnail contact sheetを作成し, consistent palette and requested ditherでindex化する]
#   引数: [frames: RGBA frames, colors: GIF palette limit, request: transparency background and dither policy]
#   戻り値: [tuple[Image.Image, ...]: palette-indexed animation frames]
# }
def _apply_global_palette(
    frames: tuple[Image.Image, ...], colors: int, request: Txt2GifRequest
) -> tuple[Image.Image, ...]:
    sample = Image.new("RGB", (64 * len(frames), 64), request.background_rgb)
    for index, frame in enumerate(frames):
        rgb = Image.new("RGB", frame.size, request.background_rgb)
        rgb.paste(frame.convert("RGB"), mask=frame.getchannel("A"))
        rgb.thumbnail((64, 64), Image.Resampling.LANCZOS)
        sample.paste(rgb, (64 * index, 0))
    palette = sample.quantize(colors=max(1, colors - 1), method=Image.Quantize.MEDIANCUT)
    palette_bytes = (palette.getpalette() or [])[:768]
    palette_bytes.extend([0] * (768 - len(palette_bytes)))
    palette.putpalette(palette_bytes[:768])
    dither = Image.Dither.NONE if request.dither is DitherMode.NONE else Image.Dither.FLOYDSTEINBERG
    output = []
    for frame in frames:
        rgba = frame.convert("RGBA")
        rgb = Image.new("RGB", rgba.size, request.background_rgb)
        rgb.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))
        indexed = rgb.quantize(palette=palette, dither=dither)
        alpha = rgba.getchannel("A")
        transparency = alpha.point(lambda value: 0 if value < 128 else 255)
        indexed.paste(255, mask=transparency.point(lambda value: 255 - value))
        output.append(indexed)
    return tuple(output)


# {
#   責務: [create_txt2gif: backend contractsをcanonical frameからGIF artifactまで実行する]
#   処理: [generate one still, extract clean plate/layers, render periodic frames and encode result]
#   引数: [request: animation constraints, backend: injected still/layer generator]
#   戻り値: [Txt2GifResult: GIF output and size/loop diagnostics]
#   エラー: [ValueError or OSError: backend, motion, or encoder failure]
# }
def create_txt2gif(
    request: Txt2GifRequest,
    backend: AnimationFrameBackend,
    *,
    progress: Callable[[str], None] | None = None,
) -> Txt2GifResult:
    if progress:
        progress("Generating canonical anime key art")
    still = backend.generate_still(request)
    if not still:
        raise ValueError("still-image backend returned no image data")
    if progress:
        progress("Extracting motion regions and static clean plate")
    clean_plate, layers = backend.extract_layers(still, request)
    if not layers:
        raise ValueError("no isolated motion regions were extracted")
    effective_request = replace(request, motion_layers=layers)
    frames = render_key_art_loop(clean_plate, layers, effective_request)
    if progress:
        progress("Encoding and validating seamless GIF")
    return encode_gif(frames, effective_request)


# {
#   責務: [_frame_error: same-sized palette framesのnormalized mean absolute pixel errorを算出する]
#   処理: [compare RGB pixel arrays and normalize error into zero through one]
#   引数: [first: loop entry frame, last: loop exit frame]
#   戻り値: [float: normalized seam error]
# }
def _frame_error(first: Image.Image, last: Image.Image) -> float:
    difference = ImageChops.difference(first.convert("RGB"), last.convert("RGB"))
    histogram = difference.histogram()
    total = sum(value * (index % 256) for index, value in enumerate(histogram))
    count = first.width * first.height * 3
    return total / (count * 255) if count else 0.0


# {
#   責務: [_atomic_write: complete GIF bytesをtemp file経由でdestinationへcommitする]
#   処理: [write, flush, fsync, replace and cleanup temporary path on error]
#   引数: [destination: final GIF path, payload: validated GIF bytes]
#   戻り値: []
#   エラー: [OSError: write/replace failed]
# }
def _atomic_write(destination: Path, payload: bytes) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(destination)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
