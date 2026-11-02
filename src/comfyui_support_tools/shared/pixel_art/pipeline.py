"""Deterministic pixel-grid rendering, editing, evaluation, and previews."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from .contracts import PixelArtCategory, PixelArtSettings, PixelEdit, PixelGrid, PixelMetric

SIZE_PRESETS = (256, 192, 128, 96, 64, 32, 16, 8)
MAX_DIMENSION = 512


# {
# 責務: [validate_settings: reject invalid shared pixel-art settings]
# 処理: [check supported size, palette, crop, dither, and zoom contracts]
# 引数: [settings: common Pixel Art Creator settings]
# 戻り値: [None: valid settings or ValueError]
# }
def validate_settings(settings: PixelArtSettings) -> None:
    try:
        PixelArtCategory(settings.category)
    except ValueError as error:
        raise ValueError("unsupported pixel-art category") from error
    if settings.custom_size is not None and (
        not isinstance(settings.custom_size, tuple) or len(settings.custom_size) != 2
    ):
        raise ValueError("custom_size must be a (width, height) integer tuple")
    width, height = settings.custom_size or (settings.size, settings.size)
    if any(not isinstance(value, int) or isinstance(value, bool) for value in (width, height)):
        raise ValueError("pixel dimensions must be integers")
    if width < 1 or height < 1 or width > MAX_DIMENSION or height > MAX_DIMENSION:
        raise ValueError(f"pixel dimensions must be within 1..{MAX_DIMENSION}")
    if settings.custom_size is None:
        if not isinstance(settings.size, int) or isinstance(settings.size, bool):
            raise ValueError("pixel size preset must be an integer")
        if settings.size not in SIZE_PRESETS:
            raise ValueError(f"unsupported pixel size preset: {settings.size}")
    if settings.palette_mode not in {"auto", "unlimited", "count", "monochrome", "custom"}:
        raise ValueError("palette_mode must be auto, unlimited, count, monochrome, or custom")
    if (
        not isinstance(settings.color_count, int)
        or isinstance(settings.color_count, bool)
        or not 1 <= settings.color_count <= 256
    ):
        raise ValueError("color_count must be within 1..256")
    if settings.palette_mode == "custom" and not settings.palette:
        raise ValueError("custom palette mode requires at least one palette color")
    if len(settings.palette) > 256 or any(
        len(color) != 4 or any(channel < 0 or channel > 255 for channel in color)
        for color in settings.palette
    ):
        raise ValueError("palette must contain at most 256 RGBA colors")
    if settings.crop_policy not in {"fit", "center_crop", "smart", "transparent_pad"}:
        raise ValueError("unsupported crop policy")
    if settings.dithering not in {"none", "floyd_steinberg", "ordered"}:
        raise ValueError("unsupported dithering mode")
    if (
        not isinstance(settings.preview_scale, int)
        or isinstance(settings.preview_scale, bool)
        or settings.preview_scale not in {1, 4, 8, 16, 32}
    ):
        raise ValueError("preview scale must be 1, 4, 8, 16, or 32")


# {
# 責務: [render_pixel_grid: normalize source art to a strict shared pixel grid]
# 処理: [crop/pad, deterministic resize, palette quantization, and alpha cleanup]
# 引数: [image: source candidate, settings: pixel constraints]
# 戻り値: [PixelGrid: strict fixed-size RGBA image]
# }
def render_pixel_grid(image: Image.Image, settings: PixelArtSettings) -> PixelGrid:
    validate_settings(settings)
    width, height = settings.custom_size or (settings.size, settings.size)
    source = image.convert("RGBA")
    binary_source_alpha = all(value in {0, 255} for value in source.getchannel("A").getdata())
    source = _prepare_canvas(source, width, height, settings.crop_policy)
    resampling = (
        Image.Resampling.NEAREST if source.size == (width, height) else Image.Resampling.LANCZOS
    )
    reduced = source.resize((width, height), resampling)
    # Keep source alpha coverage crisp; filtering it would introduce halo alpha values.
    alpha = source.getchannel("A").resize((width, height), Image.Resampling.NEAREST)
    if binary_source_alpha:
        alpha = alpha.point(lambda value: 255 if value >= 128 else 0)
    reduced.putalpha(alpha)
    reduced = _quantize(reduced, settings)
    if not settings.transparent:
        opaque = Image.new("RGBA", reduced.size, (0, 0, 0, 255))
        opaque.alpha_composite(reduced)
        reduced = opaque
    elif settings.palette_mode == "custom":
        reduced.putalpha(reduced.getchannel("A"))
    return to_grid(reduced)


# {
# 責務: [to_grid: convert PIL RGBA image to validated immutable pixels]
# 処理: [copy row-major RGBA tuples into the PixelGrid contract]
# 引数: [image: target-size image]
# 戻り値: [PixelGrid: immutable pixel state]
# }
def to_grid(image: Image.Image) -> PixelGrid:
    rgba = image.convert("RGBA")
    pixels = tuple(tuple(pixel) for pixel in rgba.getdata())
    return PixelGrid(rgba.width, rgba.height, pixels)


# {
# 責務: [from_grid: create a PIL RGBA image from PixelGrid state]
# 処理: [validate pixel dimensions and materialize row-major colors]
# 引数: [grid: immutable pixel state]
# 戻り値: [Image: exact-grid RGBA image]
# }
def from_grid(grid: PixelGrid) -> Image.Image:
    if grid.width < 1 or grid.height < 1 or len(grid.pixels) != grid.width * grid.height:
        raise ValueError("PixelGrid dimensions do not match pixel data")
    return _image_from_grid(grid)


# {
# 責務: [_image_from_grid: materialize validated PixelGrid values]
# 処理: [construct RGBA canvas and write row-major pixels]
# 引数: [grid: immutable pixel state]
# 戻り値: [Image: exact-grid RGBA image]
# }
def _image_from_grid(grid: PixelGrid) -> Image.Image:
    if (
        grid.width < 1
        or grid.height < 1
        or grid.width > MAX_DIMENSION
        or grid.height > MAX_DIMENSION
        or len(grid.pixels) != grid.width * grid.height
    ):
        raise ValueError("PixelGrid dimensions must be valid and within supported bounds")
    image = Image.new("RGBA", (grid.width, grid.height))
    image.putdata(grid.pixels)
    return image


# {
# 責務: [nearest_preview: enlarge pixels without interpolation]
# 処理: [nearest-neighbor integer scale preserving crisp cell edges]
# 引数: [grid: source grid, scale: integer zoom]
# 戻り値: [Image: enlarged preview]
# }
def nearest_preview(grid: PixelGrid, scale: int) -> Image.Image:
    if scale not in {1, 4, 8, 16, 32}:
        raise ValueError("preview scale must be 1, 4, 8, 16, or 32")
    return _image_from_grid(grid).resize(
        (grid.width * scale, grid.height * scale), Image.Resampling.NEAREST
    )


# {
# 責務: [evaluate_grid: run shared deterministic pixel-art quality metrics]
# 処理: [score palette consistency, isolated pixels, clusters, alpha, and native readability proxies]
# 引数: [grid: candidate strict grid]
# 戻り値: [PixelMetric: comparable scores, counts, and limitations]
# }
def evaluate_grid(grid: PixelGrid) -> PixelMetric:
    image = _image_from_grid(grid)
    colors = Counter(grid.pixels)
    isolated = 0
    opaque = 0
    for y in range(grid.height):
        for x in range(grid.width):
            color = grid.pixels[y * grid.width + x]
            if color[3] < 16:
                continue
            opaque += 1
            neighbors = [
                grid.pixels[ny * grid.width + nx]
                for nx, ny in _neighbors(x, y, grid.width, grid.height)
                if grid.pixels[ny * grid.width + nx][3] >= 16
            ]
            if neighbors and all(neighbor != color for neighbor in neighbors):
                isolated += 1
    alpha = image.getchannel("A")
    semi_transparent = sum(0 < value < 255 for value in alpha.getdata())
    alias_pixels = _anti_alias_pixel_count(grid, colors)
    outline_breaks = _outline_break_count(grid)
    near_duplicates = _near_duplicate_count(colors)
    edge_colors = _edge_color_count(image)
    palette_score = max(0.0, 1.0 - near_duplicates / max(len(colors), 1))
    island_score = 1.0 if opaque == 0 else max(0.0, 1.0 - isolated / opaque)
    edge_score = 1.0 if edge_colors <= 2 else max(0.0, 1.0 - (edge_colors - 2) / 64)
    alpha_score = (
        1.0 if semi_transparent == 0 else max(0.0, 1.0 - semi_transparent / max(opaque, 1))
    )
    alias_score = 1.0 if opaque == 0 else max(0.0, 1.0 - alias_pixels / opaque)
    outline_score = 1.0 if opaque == 0 else max(0.0, 1.0 - outline_breaks / opaque)
    native_score = _native_readability_proxy(image)
    values = (
        ("palette_consistency", palette_score),
        ("cluster_coherence", island_score),
        ("edge_crispness", edge_score),
        ("alpha_cleanliness", alpha_score),
        ("anti_alias_contamination", alias_score),
        ("outline_integrity_proxy", outline_score),
        ("native_size_readability_proxy", native_score),
    )
    notes = (
        "Readability is a deterministic shape/color proxy; semantic meaning requires human review.",
        "Outline quality and category suitability are not inferred as facts.",
    )
    return PixelMetric(
        sum(value for _, value in values) / len(values),
        values,
        (
            ("color_count", len(colors)),
            ("isolated_pixels", isolated),
            ("tiny_cluster_pixels", isolated),
            ("anti_alias_pixels", alias_pixels),
            ("outline_breaks", outline_breaks),
            ("near_duplicate_colors", near_duplicates),
            ("semi_transparent_pixels", semi_transparent),
        ),
        notes,
    )


# {
# 責務: [_anti_alias_pixel_count: find rare colors interpolated between local palette colors]
# 処理: [compare each pixel against neighbor-color segments as a contamination heuristic]
# 引数: [grid: strict pixel state, colors: global color frequency]
# 戻り値: [int: approximate number of anti-alias pixels]
# }
def _anti_alias_pixel_count(grid: PixelGrid, colors: Counter) -> int:
    rare = {color for color, count in colors.items() if count <= 2 and color[3] >= 128}
    found = 0
    for y in range(grid.height):
        for x in range(grid.width):
            color = grid.pixels[y * grid.width + x]
            if color not in rare:
                continue
            neighbors = [
                grid.pixels[ny * grid.width + nx]
                for nx, ny in _neighbors(x, y, grid.width, grid.height)
            ]
            rgb = color[:3]
            if any(
                _is_between_colors(rgb, left[:3], right[:3])
                for index, left in enumerate(neighbors)
                for right in neighbors[index + 1 :]
                if left != right
            ):
                found += 1
    return found


# {
# 責務: [_is_between_colors: estimate whether color lies between two palette endpoints]
# 処理: [project color into endpoint segment and bound interpolation residual]
# 引数: [color/first/second: RGB triples]
# 戻り値: [bool: likely interpolated color]
# }
def _is_between_colors(
    color: tuple[int, ...], first: tuple[int, ...], second: tuple[int, ...]
) -> bool:
    vector = tuple(b - a for a, b in zip(first, second, strict=True))
    length = sum(value * value for value in vector)
    if length < 400:
        return False
    ratio = (
        sum((value - a) * delta for value, a, delta in zip(color, first, vector, strict=True))
        / length
    )
    if not 0.15 <= ratio <= 0.85:
        return False
    residual = sum(
        (value - (a + delta * ratio)) ** 2
        for value, a, delta in zip(color, first, vector, strict=True)
    )
    return residual <= 225


# {
# 責務: [_outline_break_count: detect transparent cells splitting opaque outline runs]
# 処理: [count transparent pixel gaps bordered by opaque pixels across a cardinal axis]
# 引数: [grid: strict RGBA pixel state]
# 戻り値: [int: candidate outline breaks]
# }
def _outline_break_count(grid: PixelGrid) -> int:
    breaks = 0
    for y in range(grid.height):
        for x in range(grid.width):
            if grid.pixels[y * grid.width + x][3] >= 128:
                continue
            horizontal = (
                x > 0
                and x + 1 < grid.width
                and grid.pixels[y * grid.width + x - 1][3] >= 128
                and grid.pixels[y * grid.width + x + 1][3] >= 128
            )
            vertical = (
                y > 0
                and y + 1 < grid.height
                and grid.pixels[(y - 1) * grid.width + x][3] >= 128
                and grid.pixels[(y + 1) * grid.width + x][3] >= 128
            )
            breaks += bool(horizontal or vertical)
    return breaks


# {
# 責務: [_near_duplicate_count: count perceptually close palette color pairs]
# 処理: [measure weighted RGB distance under a fixed threshold]
# 引数: [colors: RGBA frequency map]
# 戻り値: [int: duplicate-like palette pairs]
# }
def _near_duplicate_count(colors: Counter) -> int:
    entries = [color[:3] for color, count in colors.items() if count and color[3] >= 128]
    return sum(
        1
        for index, first in enumerate(entries)
        for second in entries[index + 1 :]
        if sum(weight * (a - b) ** 2 for weight, a, b in zip((2, 4, 1), first, second, strict=True))
        < 900
    )


# {
# 責務: [apply_edits: apply reversible pixel-grid editor operations]
# 処理: [support pencil, eraser, line, rectangle, fill, palette replace, mirror, and cleanup]
# 引数: [grid: source grid, edits: ordered pixel operations]
# 戻り値: [PixelGrid: edited immutable state]
# }
def apply_edits(grid: PixelGrid, edits: tuple[PixelEdit, ...]) -> PixelGrid:
    image = _image_from_grid(grid)
    for edit in edits:
        if edit.kind in {"pencil", "eraser"}:
            _set_pixel(image, edit.x, edit.y, (0, 0, 0, 0) if edit.kind == "eraser" else edit.color)
        elif edit.kind == "line":
            ImageDraw.Draw(image).line(
                (
                    edit.x,
                    edit.y,
                    edit.x if edit.end_x is None else edit.end_x,
                    edit.y if edit.end_y is None else edit.end_y,
                ),
                fill=edit.color,
            )
        elif edit.kind == "rectangle":
            ImageDraw.Draw(image).rectangle(
                (
                    edit.x,
                    edit.y,
                    edit.x if edit.end_x is None else edit.end_x,
                    edit.y if edit.end_y is None else edit.end_y,
                ),
                fill=edit.color,
            )
        elif edit.kind == "replace_color":
            if edit.source_color is None:
                raise ValueError("replace_color requires source_color")
            image.putdata(
                tuple(
                    edit.color if tuple(pixel) == edit.source_color else pixel
                    for pixel in image.getdata()
                )
            )
        elif edit.kind == "mirror_horizontal":
            image = ImageChops.mirror(image)
        elif edit.kind == "mirror_left_to_right":
            mirrored = ImageChops.mirror(image.crop((0, 0, (image.width + 1) // 2, image.height)))
            image.paste(
                mirrored.crop((0, 0, image.width - image.width // 2, image.height)),
                (image.width // 2, 0),
            )
        elif edit.kind == "cleanup_islands":
            image = _cleanup_islands(image)
        elif edit.kind == "close_outline":
            image = _close_outline_gaps(image, edit.color)
        elif edit.kind == "remove_antialias":
            image = _quantize(
                image,
                PixelArtSettings(
                    size=grid.width,
                    custom_size=(grid.width, grid.height),
                    palette_mode="count",
                    color_count=edit.x or 16,
                    transparent=True,
                ),
            )
        elif edit.kind == "fill":
            _flood_fill(image, edit.x, edit.y, edit.color)
        else:
            raise ValueError(f"unsupported pixel edit kind: {edit.kind}")
    return to_grid(image)


# {
# 責務: [split_sprite_sheet: split a sprite atlas into strict rectangular cells]
# 処理: [validate divisibility and convert row-major cells to immutable grids]
# 引数: [image: sprite sheet, cell_width/cell_height: frame dimensions]
# 戻り値: [tuple[PixelGrid, ...]: frames in row-major order]
# }
def split_sprite_sheet(
    image: Image.Image, cell_width: int, cell_height: int
) -> tuple[PixelGrid, ...]:
    if cell_width < 1 or cell_height < 1 or image.width % cell_width or image.height % cell_height:
        raise ValueError("sprite-sheet dimensions must be divisible by positive cell dimensions")
    frames = []
    for top in range(0, image.height, cell_height):
        for left in range(0, image.width, cell_width):
            frames.append(to_grid(image.crop((left, top, left + cell_width, top + cell_height))))
    return tuple(frames)


# {
# 責務: [combine_sprite_sheet: pack equal-size grids in deterministic row-major order]
# 処理: [validate cell counts and compose a fixed-column RGBA atlas]
# 引数: [frames: image grids, columns: cells per row]
# 戻り値: [Image: combined RGBA sprite sheet]
# }
def combine_sprite_sheet(frames: tuple[PixelGrid, ...], columns: int) -> Image.Image:
    if not frames or columns < 1:
        raise ValueError("sprite sheet needs frames and a positive column count")
    width, height = frames[0].width, frames[0].height
    if any(frame.width != width or frame.height != height for frame in frames):
        raise ValueError("all sprite-sheet frames must have equal dimensions")
    rows = (len(frames) + columns - 1) // columns
    atlas = Image.new("RGBA", (columns * width, rows * height), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        atlas.alpha_composite(
            _image_from_grid(frame), ((index % columns) * width, (index // columns) * height)
        )
    return atlas


# {
# 責務: [load_palette: import a portable RGB/RGBA palette JSON file]
# 処理: [validate schema, dimensions, channel ranges, and maximum color count]
# 引数: [path: palette JSON file path]
# 戻り値: [tuple[RGBA, ...]: validated palette colors]
# }
def load_palette(path: Path) -> tuple[tuple[int, int, int, int], ...]:
    palette_path = Path(path)
    if palette_path.stat().st_size > 64 * 1024:
        raise ValueError("palette file is too large")
    raw = json.loads(palette_path.read_text(encoding="utf-8"))
    colors = raw.get("colors_rgba", raw) if isinstance(raw, dict) else raw
    if not isinstance(colors, list) or not colors or len(colors) > 256:
        raise ValueError("palette file must contain 1..256 colors")
    result = []
    for color in colors:
        if (
            not isinstance(color, list)
            or len(color) not in {3, 4}
            or any(type(value) is not int or not 0 <= value <= 255 for value in color)
        ):
            raise ValueError("palette colors must be RGB or RGBA byte arrays")
        result.append(tuple(color) if len(color) == 4 else (*color, 255))
    return tuple(result)


# {
# 責務: [palette_from_reference: extract a bounded palette from a reference image]
# 処理: [use deterministic median-cut quantization and discard unused entries]
# 引数: [image: reference image, color_count: desired palette size]
# 戻り値: [tuple[RGBA, ...]: extracted colors]
# }
def palette_from_reference(
    image: Image.Image, color_count: int = 16
) -> tuple[tuple[int, int, int, int], ...]:
    if not 1 <= color_count <= 256:
        raise ValueError("color_count must be within 1..256")
    quantized = (
        image.convert("RGBA")
        .convert("RGB")
        .quantize(colors=color_count, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    )
    palette = quantized.getpalette() or []
    used = sorted(set(quantized.getdata()))
    return tuple(
        (*palette[index * 3 : index * 3 + 3], 255)
        for index in used
        if len(palette[index * 3 : index * 3 + 3]) == 3
    )


# {
# 責務: [_prepare_canvas: crop/pad source art without stretching composition]
# 処理: [fit, center/smart crop, or transparent padding to target aspect ratio]
# 引数: [image: RGBA source, width/height: target dimensions, policy: crop policy]
# 戻り値: [Image: aspect-preserving source canvas]
# }
def _prepare_canvas(image: Image.Image, width: int, height: int, policy: str) -> Image.Image:
    target_ratio = width / height
    source_ratio = image.width / image.height
    if policy == "transparent_pad":
        canvas = Image.new("RGBA", (max(image.width, image.height),) * 2, (0, 0, 0, 0))
        canvas.alpha_composite(
            image, ((canvas.width - image.width) // 2, (canvas.height - image.height) // 2)
        )
        return canvas
    if policy in {"center_crop", "smart"}:
        if source_ratio > target_ratio:
            crop_width = max(1, round(image.height * target_ratio))
            left = (image.width - crop_width) // 2
            if policy == "smart" and image.getchannel("A").getbbox():
                bounds = image.getchannel("A").getbbox()
                left = min(
                    max(bounds[0] + (bounds[2] - bounds[0] - crop_width) // 2, 0),
                    image.width - crop_width,
                )
            return image.crop((left, 0, left + crop_width, image.height))
        crop_height = max(1, round(image.width / target_ratio))
        top = (image.height - crop_height) // 2
        if policy == "smart" and image.getchannel("A").getbbox():
            bounds = image.getchannel("A").getbbox()
            top = min(
                max(bounds[1] + (bounds[3] - bounds[1] - crop_height) // 2, 0),
                image.height - crop_height,
            )
        return image.crop((0, top, image.width, top + crop_height))
    fitted = image.copy()
    fitted.thumbnail((width, height), Image.Resampling.LANCZOS)
    background = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    background.alpha_composite(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    return background


# {
# 責務: [_quantize: reduce colors with alpha-safe palette constraints]
# 処理: [apply fixed, monochrome, or median-cut palette with selected dithering]
# 引数: [image: exact target canvas, settings: palette and dither policy]
# 戻り値: [Image: RGBA image containing no more selected opaque colors]
# }
def _quantize(image: Image.Image, settings: PixelArtSettings) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    rgb = rgba.convert("RGB")
    if settings.palette_mode == "unlimited":
        quantized = rgb
    elif settings.palette_mode == "custom":
        palette = [color[:3] for color in settings.palette]
        quantized = _map_palette(rgb, palette)
    elif settings.palette_mode == "monochrome":
        quantized = rgb.convert("L").convert("RGB")
        quantized = quantized.quantize(
            colors=2, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        ).convert("RGB")
    else:
        count = (
            settings.color_count
            if settings.palette_mode == "count"
            else min(32, settings.color_count)
        )
        dither = (
            Image.Dither.FLOYDSTEINBERG
            if settings.dithering == "floyd_steinberg"
            else Image.Dither.NONE
        )
        quantized = rgb.quantize(
            colors=count, method=Image.Quantize.MEDIANCUT, dither=dither
        ).convert("RGB")
        if settings.dithering == "ordered":
            quantized = _ordered_dither(rgb, count)
    result = quantized.convert("RGBA")
    alpha_values = tuple(alpha.getdata())
    result.putalpha(Image.new("L", result.size))
    result.putdata(
        tuple((*pixel[:3], a) for pixel, a in zip(result.getdata(), alpha_values, strict=True))
    )
    if settings.transparent:
        result.putdata(
            tuple((0, 0, 0, 0) if pixel[3] == 0 else pixel for pixel in result.getdata())
        )
    return result


# {
# 責務: [_map_palette: map every source pixel to nearest explicit palette color]
# 処理: [use perceptual-ish weighted RGB distance and preserve alpha separately]
# 引数: [image: RGB source, palette: configured RGB colors]
# 戻り値: [Image: palette-mapped RGB image]
# }
def _map_palette(image: Image.Image, palette: list[tuple[int, int, int]]) -> Image.Image:
    if not palette:
        raise ValueError("palette cannot be empty")
    output = []
    mapped = {}
    for red, green, blue in image.getdata():
        source = (red, green, blue)
        color = mapped.get(source)
        if color is None:
            color = min(
                palette,
                key=lambda item: (
                    2 * (item[0] - red) ** 2 + 4 * (item[1] - green) ** 2 + (item[2] - blue) ** 2
                ),
            )
            mapped[source] = color
        output.append(color)
    result = Image.new("RGB", image.size)
    result.putdata(output)
    return result


# {
# 責務: [_ordered_dither: apply a bounded 4x4 Bayer pattern before quantization]
# 処理: [add deterministic cell-aligned luminance thresholds and quantize]
# 引数: [image: source RGB image, count: palette color limit]
# 戻り値: [Image: ordered-dithered RGB image]
# }
def _ordered_dither(image: Image.Image, count: int) -> Image.Image:
    matrix = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
    pixels = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = image.getpixel((x, y))
            threshold = (matrix[y % 4][x % 4] - 7.5) * (32 / max(count, 1))
            pixels.append(
                tuple(max(0, min(255, round(value + threshold))) for value in (red, green, blue))
            )
    result = Image.new("RGB", image.size)
    result.putdata(pixels)
    return result.quantize(
        colors=count, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    ).convert("RGB")


# {
# 責務: [_neighbors: yield valid eight-connected pixel coordinates]
# 処理: [exclude the current coordinate and image boundaries]
# 引数: [x/y: center coordinate, width/height: grid size]
# 戻り値: [iterator: surrounding pixel coordinates]
# }
def _neighbors(x: int, y: int, width: int, height: int):
    return (
        (nx, ny)
        for ny in range(max(0, y - 1), min(height, y + 2))
        for nx in range(max(0, x - 1), min(width, x + 2))
        if (nx, ny) != (x, y)
    )


# {
# 責務: [_edge_color_count: measure unique colors touching canvas boundaries]
# 処理: [collect visible edge colors as an anti-alias contamination proxy]
# 引数: [image: target-size RGBA candidate]
# 戻り値: [int: number of distinct edge colors]
# }
def _edge_color_count(image: Image.Image) -> int:
    pixels = image.load()
    colors = {pixels[x, 0] for x in range(image.width)} | {
        pixels[x, image.height - 1] for x in range(image.width)
    }
    colors |= {pixels[0, y] for y in range(image.height)} | {
        pixels[image.width - 1, y] for y in range(image.height)
    }
    return len(colors)


# {
# 責務: [_native_readability_proxy: estimate shape contrast at native dimensions]
# 処理: [score opaque occupancy and color/alpha contrast without semantic claims]
# 引数: [image: native-size candidate]
# 戻り値: [float: normalized contrast/readability proxy]
# }
def _native_readability_proxy(image: Image.Image) -> float:
    alpha = image.getchannel("A")
    occupancy = sum(value >= 128 for value in alpha.getdata()) / max(image.width * image.height, 1)
    colors = len(set(image.convert("RGB").getdata()))
    if occupancy == 0:
        return 0.0
    return min(1.0, (0.25 + min(colors, 8) / 16) * min(1.0, occupancy * 2))


# {
# 責務: [_set_pixel: write one edit only when coordinate is on the canvas]
# 処理: [bounds check and set exact RGBA cell]
# 引数: [image: mutable canvas, x/y: cell coordinate, color: RGBA value]
# 戻り値: [None: updates image in place]
# }
def _set_pixel(image: Image.Image, x: int, y: int, color: tuple[int, int, int, int]) -> None:
    if not (0 <= x < image.width and 0 <= y < image.height):
        raise ValueError("pixel edit coordinate is outside grid")
    image.putpixel((x, y), color)


# {
# 責務: [_flood_fill: fill the connected region of the selected original color]
# 処理: [bounded iterative four-connected traversal]
# 引数: [image: mutable canvas, x/y: seed, color: replacement RGBA]
# 戻り値: [None: updates image in place]
# }
def _flood_fill(image: Image.Image, x: int, y: int, color: tuple[int, int, int, int]) -> None:
    if not (0 <= x < image.width and 0 <= y < image.height):
        raise ValueError("pixel edit coordinate is outside grid")
    source = image.getpixel((x, y))
    if source == color:
        return
    pending = [(x, y)]
    visited = set()
    while pending:
        px, py = pending.pop()
        if (px, py) in visited or image.getpixel((px, py)) != source:
            continue
        visited.add((px, py))
        image.putpixel((px, py), color)
        pending.extend(
            (nx, ny)
            for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1))
            if 0 <= nx < image.width and 0 <= ny < image.height
        )


# {
# 責務: [_cleanup_islands: conservatively replace one-pixel clusters]
# 処理: [only alter pixels surrounded by one unanimous opaque neighbor color]
# 引数: [image: candidate RGBA image]
# 戻り値: [Image: island-cleaned candidate]
# }
def _cleanup_islands(image: Image.Image) -> Image.Image:
    original = image.copy()
    output = image.copy()
    source, target = original.load(), output.load()
    for y in range(image.height):
        for x in range(image.width):
            current = source[x, y]
            neighbors = [
                source[nx, ny]
                for nx, ny in _neighbors(x, y, image.width, image.height)
                if source[nx, ny][3] >= 128
            ]
            if current[3] >= 128 and len(neighbors) >= 5:
                common, count = Counter(neighbors).most_common(1)[0]
                if count >= 5 and common != current:
                    target[x, y] = common
    return output


# {
# 責務: [_close_outline_gaps: conservatively close one-cell transparent outline gaps]
# 処理: [fill only transparent cells with at least three connected opaque neighbors]
# 引数: [image: source sprite, color: optional fill color or transparent color-sampling sentinel]
# 戻り値: [Image: outline candidate]
# }
def _close_outline_gaps(image: Image.Image, color: tuple[int, int, int, int]) -> Image.Image:
    original = image.copy()
    output = image.copy()
    source, target = original.load(), output.load()
    for y in range(image.height):
        for x in range(image.width):
            if source[x, y][3] >= 128:
                continue
            neighbors = [
                source[nx, ny]
                for nx, ny in _neighbors(x, y, image.width, image.height)
                if source[nx, ny][3] >= 128
            ]
            if len(neighbors) >= 3:
                selected = color if color[3] else Counter(neighbors).most_common(1)[0][0]
                target[x, y] = selected
    return output
