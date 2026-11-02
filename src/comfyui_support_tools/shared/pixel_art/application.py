"""One application facade for text generation, image conversion, and retouch."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageFilter

from .contracts import (
    PixelArtRequest,
    PixelArtResult,
    PixelArtSettings,
    PixelEdit,
    PixelGrid,
    PixelTextBackend,
)
from .pipeline import (
    apply_edits,
    evaluate_grid,
    from_grid,
    nearest_preview,
    palette_from_reference,
    render_pixel_grid,
    split_sprite_sheet,
    to_grid,
    validate_settings,
)

MAX_PROJECT_HISTORY = 1000


# {
# 責務: [PixelArtApplication: expose the three shared pixel-art workflows]
# フィールド: [text backend: optional replaceable generative model adapter]
# 処理: [share rendering, evaluator, settings, metadata, and project session behavior]
# }
class PixelArtApplication:
    # {
    # 責務: [__init__: construct application with an optional text generator]
    # 処理: [store adapter and keep deterministic workflows available without a model]
    # 引数: [text_backend: optional generator implementing PixelTextBackend]
    # 戻り値: [None: initialized application]
    # }
    def __init__(self, text_backend: PixelTextBackend | None = None):
        self.text_backend = text_backend

    # {
    # 責務: [text_to_pixel: create ranked strict-grid candidates from a prompt]
    # 処理: [call backend then run common quantization/evaluation for every candidate]
    # 引数: [request: prompt and shared pixel settings]
    # 戻り値: [results: candidates ordered by deterministic pixel score]
    # }
    def text_to_pixel(self, request: PixelArtRequest) -> tuple[PixelArtResult, ...]:
        validate_settings(request.settings)
        if self.text_backend is None:
            raise RuntimeError("text generation requires a configured PixelTextBackend")
        if (
            not isinstance(request.prompt, str)
            or not request.prompt.strip()
            or len(request.prompt) > 20_000
            or not isinstance(request.negative_prompt, str)
            or len(request.negative_prompt) > 10_000
            or not isinstance(request.style, str)
            or not request.style.strip()
            or len(request.style) > 64
            or request.outline_policy not in {"clear_outline", "soft_outline", "no_outline", "auto"}
            or request.shading_level not in {"flat", "low", "medium", "high"}
            or request.detail_level not in {"auto", "minimal", "balanced", "rich"}
            or not isinstance(request.candidate_count, int)
            or isinstance(request.candidate_count, bool)
            or not 1 <= request.candidate_count <= 16
            or (
                request.seed is not None
                and (
                    not isinstance(request.seed, int)
                    or isinstance(request.seed, bool)
                    or not 0 <= request.seed < 2**32
                )
            )
        ):
            raise ValueError("prompt settings, seed, or candidate_count are invalid")
        drafts = self.text_backend.generate(request)
        if not drafts:
            raise ValueError("text backend returned no candidates")
        results = tuple(
            _make_result(
                image,
                request.settings,
                {
                    "workflow": "text",
                    "candidate": index,
                    "prompt": request.prompt,
                    "style": request.style,
                    "outline_policy": request.outline_policy,
                    "shading_level": request.shading_level,
                    "detail_level": request.detail_level,
                    "seed": request.seed,
                },
            )
            for index, image in enumerate(drafts[: request.candidate_count])
        )
        return tuple(sorted(results, key=lambda result: result.metric.score, reverse=True))

    # {
    # 責務: [image_to_pixel: structure-preserving image conversion entry]
    # 処理: [apply shared crop/grid/palette/dither policies and evaluate result]
    # 引数: [image: source artwork, settings: shared pixel-art constraints, mode: conversion intent]
    # 戻り値: [PixelArtResult: strict-grid image and quality report]
    # }
    def image_to_pixel(
        self, image: Image.Image, settings: PixelArtSettings, mode: str = "faithful"
    ) -> PixelArtResult:
        if mode not in {"faithful", "simplified", "sprite", "icon", "palette_constrained"}:
            raise ValueError("unsupported image-to-pixel mode")
        validate_settings(settings)
        source = image.convert("RGBA")
        active_settings = settings
        if mode == "simplified":
            rgb = source.convert("RGB").filter(ImageFilter.MedianFilter(3))
            source = Image.merge("RGBA", (*rgb.split(), source.getchannel("A")))
        elif mode == "sprite":
            source = _crop_visible_subject(source)
            active_settings = replace(settings, crop_policy="transparent_pad")
        elif mode == "icon":
            active_settings = replace(settings, crop_policy="center_crop")
        elif mode == "palette_constrained" and settings.palette_mode != "custom":
            raise ValueError("palette_constrained mode requires a loaded custom palette")
        return _make_result(
            source,
            active_settings,
            {"workflow": "image", "mode": mode, "source_size": image.size},
        )

    # {
    # 責務: [image_to_pixel_candidates: create comparable structure/palette conversion variants]
    # 処理: [run faithful, simplified, silhouette-first, and palette-first deterministic modes]
    # 引数: [image: source artwork, settings: shared pixel-grid constraints]
    # 戻り値: [tuple[(mode, result), ...]: named candidates for human comparison]
    # }
    def image_to_pixel_candidates(self, image, settings):
        silhouette_settings = replace(settings, palette_mode="monochrome", dithering="none")
        palette_settings = replace(
            settings,
            palette_mode="custom" if settings.palette_mode == "custom" else "count",
            color_count=min(settings.color_count, 8),
            dithering="none",
        )
        silhouette = self.image_to_pixel(image, silhouette_settings, "faithful")
        silhouette.metadata["mode"] = "silhouette_first"
        palette = self.image_to_pixel(image, palette_settings, "faithful")
        palette.metadata["mode"] = "palette_first"
        faithful = self.image_to_pixel(image, settings, "faithful")
        candidates = (
            ("faithful", faithful),
            ("simplified", self.image_to_pixel(image, settings, "simplified")),
            ("silhouette_first", silhouette),
            ("palette_first", palette),
        )
        for mode, result in candidates:
            result.metadata.update(_diff_metadata(faithful.grid, result.grid))
            result.metadata["candidate_mode"] = mode
        return candidates

    # {
    # 責務: [batch_image_to_pixel: convert an input folder with reproducible per-file outputs]
    # 処理: [optionally recurse, preserve relative paths, refuse overwrite, and write a manifest]
    # 引数: [source_dir: image folder, output_dir: target root, settings: conversion settings, recursive: recurse flag]
    # 戻り値: [Path: JSON manifest with output records and pixel metrics]
    # }
    def batch_image_to_pixel(
        self, source_dir, output_dir, settings, recursive=False, mode="faithful"
    ):
        source_root = Path(source_dir).resolve(strict=True)
        output_root = Path(output_dir).resolve()
        if (
            not source_root.is_dir()
            or output_root == source_root
            or source_root in output_root.parents
        ):
            raise ValueError("batch output must be outside the source folder")
        if mode not in {"faithful", "simplified", "sprite", "icon", "palette_constrained"}:
            raise ValueError("unsupported image-to-pixel mode")
        validate_settings(settings)
        patterns = source_root.rglob("*") if recursive else source_root.glob("*")
        paths = tuple(
            sorted(
                path
                for path in patterns
                if path.is_file()
                and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
            )
        )
        if not paths:
            raise ValueError("batch input contains no supported images")
        records = []
        width, height = settings.custom_size or (settings.size, settings.size)
        for path in paths:
            relative = path.relative_to(source_root)
            with Image.open(path) as image:
                result = self.image_to_pixel(image.copy(), settings, mode)
            exported = self.export(
                result, output_root / f"{width}x{height}" / relative.parent, path.stem
            )
            records.append(
                {
                    "source": relative.as_posix(),
                    "outputs": [item.relative_to(output_root).as_posix() for item in exported],
                    "color_count": dict(result.metric.counts)["color_count"],
                    "score_proxy": result.metric.score,
                }
            )
        manifest = output_root / "batch-manifest.json"
        payload = (
            json.dumps(
                {"schema_version": 1, "mode": mode, "records": records},
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
        _write_reserved((manifest,), (payload.encode("utf-8"),))
        return manifest

    # {
    # 責務: [retouch: apply pixel-precise edits and run common evaluation]
    # 処理: [apply ordered reversible edits on immutable grid state]
    # 引数: [grid: source pixel grid, edits: ordered editing actions]
    # 戻り値: [PixelArtResult: edited grid and quality report]
    # }
    def retouch(self, grid: PixelGrid, edits: tuple[PixelEdit, ...]) -> PixelArtResult:
        edited = apply_edits(grid, edits)
        return _result_for_grid(edited, {"workflow": "retouch", "edit_count": len(edits)})

    # {
    # 責務: [split_sprite_sheet: expose basic atlas inspection to shared pixel tools]
    # 処理: [delegate row-major cell extraction to the shared grid pipeline]
    # 引数: [image: atlas image, cell_width/cell_height: exact frame size]
    # 戻り値: [tuple[PixelGrid, ...]: extracted animation or tile cells]
    # }
    def split_sprite_sheet(
        self, image: Image.Image, cell_width: int, cell_height: int
    ) -> tuple[PixelGrid, ...]:
        return split_sprite_sheet(image, cell_width, cell_height)

    # {
    # 責務: [extract_palette: create a reusable palette from a reference image]
    # 処理: [expose deterministic palette extraction beside import/export workflow]
    # 引数: [image: palette reference, color_count: maximum palette size]
    # 戻り値: [tuple[RGBA, ...]: reusable color values]
    # }
    def extract_palette(
        self, image: Image.Image, color_count: int = 16
    ) -> tuple[tuple[int, int, int, int], ...]:
        return palette_from_reference(image, color_count)

    # {
    # 責務: [cleanup_candidates: compare conservative to aggressive shared cleanup variants]
    # 処理: [generate isolated-pixel, palette reduction, and outline-repair candidates]
    # 引数: [grid: source pixel art]
    # 戻り値: [tuple[(mode, result), ...]: reviewable cleanup candidates]
    # }
    def cleanup_candidates(self, grid: PixelGrid) -> tuple[tuple[str, PixelArtResult], ...]:
        modes = (
            ("conservative", (PixelEdit("cleanup_islands"),)),
            ("standard", (PixelEdit("cleanup_islands"), PixelEdit("remove_antialias", x=16))),
            (
                "aggressive",
                (
                    PixelEdit("cleanup_islands"),
                    PixelEdit("remove_antialias", x=8),
                    PixelEdit("close_outline"),
                ),
            ),
        )
        candidates = []
        for mode, edits in modes:
            result = self.retouch(grid, edits)
            result.metadata.update(_diff_metadata(grid, result.grid))
            result.metadata["cleanup_mode"] = mode
            result.metadata["semantic_confidence"] = None
            candidates.append((mode, result))
        return tuple(candidates)

    # {
    # 責務: [replace_palette_color: replace one exact color throughout a pixel grid]
    # 処理: [apply a reversible global palette substitution and report the result]
    # 引数: [grid: source art, source: exact color, target: replacement RGBA color]
    # 戻り値: [PixelArtResult: edited grid with common pixel metrics]
    # }
    def replace_palette_color(self, grid, source, target):
        if source == target:
            return self.retouch(grid, ())
        return self.retouch(grid, (PixelEdit("replace_color", color=target, source_color=source),))

    # {
    # 責務: [reduce_palette: quantize a pixel grid to a bounded color count]
    # 処理: [preserve native dimensions and transparency while using shared quantization]
    # 引数: [grid: source art, color_count: requested opaque palette size]
    # 戻り値: [PixelArtResult: reduced-palette art and metrics]
    # }
    def reduce_palette(self, grid, color_count):
        if not 1 <= color_count <= 256:
            raise ValueError("color_count must be in 1..256")
        settings = PixelArtSettings(
            size=max(grid.width, grid.height),
            custom_size=(grid.width, grid.height),
            palette_mode="count",
            color_count=color_count,
            transparent=True,
        )
        return _make_result(
            from_grid(grid), settings, {"workflow": "retouch", "operation": "reduce_palette"}
        )

    # {
    # 責務: [cleanup_transparent_edges: remove partially transparent pixel edges]
    # 処理: [map alpha below threshold to transparent and remaining alpha to opaque]
    # 引数: [grid: source art, threshold: alpha cutoff from 1 through 254]
    # 戻り値: [PixelArtResult: binary-alpha retouch result]
    # }
    def cleanup_transparent_edges(self, grid, threshold=128):
        if not 1 <= threshold <= 254:
            raise ValueError("threshold must be in 1..254")
        pixels = tuple(
            color if color[3] in {0, 255} else (*color[:3], 0 if color[3] < threshold else 255)
            for color in grid.pixels
        )
        return _result_for_grid(
            PixelGrid(grid.width, grid.height, pixels),
            {"workflow": "retouch", "operation": "clean_alpha_edges"},
        )

    # {
    # 責務: [new_project: create an undoable retouch session from a result]
    # 処理: [initialize project history with the initial pixel grid]
    # 引数: [result: initial pixel art state]
    # 戻り値: [PixelProject: undo/redo project session]
    # }
    def new_project(self, result: PixelArtResult) -> PixelProject:
        return PixelProject([result.grid], 0, result.metadata.get("settings", {}))

    # {
    # 責務: [export: write transparent PNG, palette, and JSON metadata]
    # 処理: [atomically reserve all output paths and write a reproducible export]
    # 引数: [result: completed candidate, output_dir: destination directory, stem: output name]
    # 戻り値: [paths: PNG, palette JSON, and metadata JSON destinations]
    # }
    def export(
        self, result: PixelArtResult, output_dir: Path, stem: str
    ) -> tuple[Path, Path, Path]:
        if not stem or Path(stem).name != stem or stem in {".", ".."}:
            raise ValueError("export stem must be a plain file name")
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        paths = (
            destination / f"{stem}.png",
            destination / f"{stem}.palette.json",
            destination / f"{stem}.pixel.json",
        )
        palette = sorted({tuple(color) for color in result.grid.pixels})
        metadata = {
            **result.metadata,
            "schema_version": 1,
            "width": result.grid.width,
            "height": result.grid.height,
            "metrics": {
                "score": result.metric.score,
                "values": dict(result.metric.values),
                "counts": dict(result.metric.counts),
                "notes": result.metric.notes,
            },
        }
        _write_reserved(
            paths,
            (
                _png_bytes(from_grid(result.grid)),
                (json.dumps({"colors_rgba": palette}, indent=2) + "\n").encode("utf-8"),
                (json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode(
                    "utf-8"
                ),
            ),
        )
        return paths


# {
# 責務: [PixelProject: maintain undo/redo states and save project snapshots]
# フィールド: [states: immutable grid history, cursor: current state index]
# 処理: [edit history, undo/redo, and portable project persistence]
# }
class PixelProject:
    # {
    # 責務: [__init__: create project state history]
    # 処理: [keep snapshots and current cursor]
    # 引数: [states: initial grid snapshots, cursor: current snapshot position]
    # 戻り値: [None: initialized project]
    # }
    def __init__(self, states: list[PixelGrid], cursor: int, settings: object = None):
        if not states or len(states) > MAX_PROJECT_HISTORY or not 0 <= cursor < len(states):
            raise ValueError("project history requires a valid current snapshot")
        for state in states:
            from_grid(state)
        self._states = states
        self._cursor = cursor
        self._settings = settings or {}

    # {
    # 責務: [grid: expose the current project snapshot]
    # 処理: [read current immutable grid from history]
    # 引数: [None: no inputs]
    # 戻り値: [PixelGrid: current snapshot]
    # }
    @property
    def grid(self) -> PixelGrid:
        return self._states[self._cursor]

    # {
    # 責務: [can_undo: indicate whether an earlier snapshot exists]
    # 処理: [compare cursor to history beginning]
    # 引数: [None: no inputs]
    # 戻り値: [bool: undo availability]
    # }
    @property
    def can_undo(self) -> bool:
        return self._cursor > 0

    # {
    # 責務: [can_redo: indicate whether a later snapshot exists]
    # 処理: [compare cursor to history end]
    # 引数: [None: no inputs]
    # 戻り値: [bool: redo availability]
    # }
    @property
    def can_redo(self) -> bool:
        return self._cursor < len(self._states) - 1

    # {
    # 責務: [apply: append one edited snapshot and discard redo branch]
    # 処理: [run pixel edits on current grid and update history cursor]
    # 引数: [edits: reversible edit actions]
    # 戻り値: [PixelGrid: new current state]
    # }
    def apply(self, edits: tuple[PixelEdit, ...]) -> PixelGrid:
        updated = apply_edits(self.grid, edits)
        return self.apply_grid(updated)

    # {
    # 責務: [apply_grid: append a reviewed candidate grid to undoable project history]
    # 処理: [validate dimensions and pixels before replacing the current snapshot]
    # 引数: [updated: explicitly accepted candidate state]
    # 戻り値: [PixelGrid: new current project snapshot]
    # }
    def apply_grid(self, updated: PixelGrid) -> PixelGrid:
        if (updated.width, updated.height) != (self.grid.width, self.grid.height):
            raise ValueError("candidate grid dimensions must match the active project")
        from_grid(updated)
        self._states = self._states[: self._cursor + 1] + [updated]
        self._cursor += 1
        if len(self._states) > MAX_PROJECT_HISTORY:
            del self._states[0]
            self._cursor -= 1
        return updated

    # {
    # 責務: [undo: restore the previous pixel snapshot]
    # 処理: [move cursor back when history permits]
    # 引数: [None: no inputs]
    # 戻り値: [PixelGrid: current state after undo]
    # }
    def undo(self) -> PixelGrid:
        if self.can_undo:
            self._cursor -= 1
        return self.grid

    # {
    # 責務: [redo: restore the next pixel snapshot]
    # 処理: [move cursor forward when a redo branch exists]
    # 引数: [None: no inputs]
    # 戻り値: [PixelGrid: current state after redo]
    # }
    def redo(self) -> PixelGrid:
        if self.can_redo:
            self._cursor += 1
        return self.grid

    # {
    # 責務: [save: persist all snapshots to a portable project directory]
    # 処理: [write PNG snapshot history and manifest through a sibling temporary directory]
    # 引数: [path: new project directory path]
    # 戻り値: [Path: saved project directory]
    # }
    def save(self, path: Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir()
        try:
            snapshots = destination / "snapshots"
            snapshots.mkdir()
            for index, grid in enumerate(self._states):
                from_grid(grid).save(snapshots / f"{index:04d}.png", format="PNG")
            manifest = {
                "schema_version": 1,
                "cursor": self._cursor,
                "snapshots": len(self._states),
                "current_size": [self.grid.width, self.grid.height],
                "settings": self._settings,
            }
            manifest_path = destination / ".project.json.tmp"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            os.replace(manifest_path, destination / "project.json")
        except BaseException:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return destination

    # {
    # 責務: [load: restore project state history from a saved directory]
    # 処理: [validate manifest/snapshot bounds and rebuild immutable grids]
    # 引数: [path: project directory]
    # 戻り値: [PixelProject: restored undo/redo session]
    # }
    @classmethod
    def load(cls, path: Path) -> PixelProject:
        root = Path(path)
        manifest = json.loads((root / "project.json").read_text(encoding="utf-8"))
        count = manifest.get("snapshots")
        cursor = manifest.get("cursor")
        if (
            not isinstance(count, int)
            or not 1 <= count <= 1000
            or not isinstance(cursor, int)
            or not 0 <= cursor < count
        ):
            raise ValueError("invalid pixel project manifest")
        states = []
        for index in range(count):
            with Image.open(root / "snapshots" / f"{index:04d}.png") as image:
                states.append(to_grid(image.copy()))
        return cls(states, cursor, manifest.get("settings", {}))


# {
# 責務: [_make_result: render and evaluate a single source image]
# 処理: [share strict-grid processing and nearest-neighbor preview creation]
# 引数: [image: source image, settings: pixel rules, metadata: workflow provenance]
# 戻り値: [PixelArtResult: common application result]
# }
def _make_result(
    image: Image.Image, settings: PixelArtSettings, metadata: dict[str, object]
) -> PixelArtResult:
    grid = render_pixel_grid(image, settings)
    return _result_for_grid(
        grid,
        {
            **metadata,
            "settings": {
                "size": settings.size,
                "custom_size": settings.custom_size,
                "category": getattr(settings.category, "value", settings.category),
                "palette_mode": settings.palette_mode,
                "color_count": settings.color_count,
                "palette": settings.palette,
                "transparent": settings.transparent,
                "crop_policy": settings.crop_policy,
                "dithering": settings.dithering,
            },
        },
        settings.preview_scale,
    )


# {
# 責務: [_result_for_grid: package a grid with common metrics and preview]
# 処理: [evaluate strict grid and create crisp scale preview]
# 引数: [grid: immutable pixel image, metadata: workflow provenance, scale: preview zoom]
# 戻り値: [PixelArtResult: evaluated candidate]
# }
def _result_for_grid(
    grid: PixelGrid, metadata: dict[str, object], scale: int = 8
) -> PixelArtResult:
    return PixelArtResult(grid, evaluate_grid(grid), nearest_preview(grid, scale), metadata)


# {
# 責務: [_crop_visible_subject: trim transparent margins around a sprite subject]
# 処理: [crop alpha bounds with a small proportional margin and retain RGBA content]
# 引数: [image: source RGBA artwork]
# 戻り値: [Image: bounded visible subject or unchanged fully opaque image]
# }
def _crop_visible_subject(image):
    alpha = image.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None or bounds == (0, 0, image.width, image.height):
        return image
    left, top, right, bottom = bounds
    margin = max(1, round(max(right - left, bottom - top) * 0.05))
    return image.crop(
        (
            max(0, left - margin),
            max(0, top - margin),
            min(image.width, right + margin),
            min(image.height, bottom + margin),
        )
    )


# {
# 責務: [_diff_metadata: summarize pixel changes and connected changed regions]
# 処理: [count changed cells and group adjacent changes into compact bounding boxes]
# 引数: [before: source grid, after: candidate grid]
# 戻り値: [dict[str, object]: counts, palette sizes, and changed-region bounds]
# }
def _diff_metadata(before, after):
    if (before.width, before.height) != (after.width, after.height):
        raise ValueError("pixel diff requires grids with matching dimensions")
    changed = {
        (index % before.width, index // before.width)
        for index, (left, right) in enumerate(zip(before.pixels, after.pixels, strict=True))
        if left != right
    }
    regions = []
    while changed:
        seed = changed.pop()
        component = {seed}
        pending = [seed]
        while pending:
            x, y = pending.pop()
            neighbors = {(x + dx, y + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy}
            adjacent = changed & neighbors
            changed.difference_update(adjacent)
            component.update(adjacent)
            pending.extend(adjacent)
        xs = [point[0] for point in component]
        ys = [point[1] for point in component]
        regions.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    return {
        "changed_pixels": sum(
            left != right for left, right in zip(before.pixels, after.pixels, strict=True)
        ),
        "changed_regions": tuple(sorted(regions, key=lambda region: (region[1], region[0]))),
        "palette_before": len(set(before.pixels)),
        "palette_after": len(set(after.pixels)),
    }


# {
# 責務: [_png_bytes: encode PNG bytes in memory]
# 処理: [serialize image using lossless transparent-capable PNG format]
# 引数: [image: RGBA pixel image]
# 戻り値: [bytes: encoded PNG]
# }
def _png_bytes(image: Image.Image) -> bytes:
    import io

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


# {
# 責務: [_write_reserved: atomically reserve and write a group of export files]
# 処理: [prevent overwrite and clean partial output on failures]
# 引数: [paths: destinations, payloads: corresponding bytes]
# 戻り値: [None: files are written in place]
# }
def _write_reserved(paths: tuple[Path, ...], payloads: tuple[bytes, ...]) -> None:
    if len(paths) != len(payloads):
        raise ValueError("path and payload counts must match")
    owned = []
    temporaries = []
    try:
        for path in paths:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            owned.append(path)
        for path, payload in zip(paths, payloads, strict=True):
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as stream:
                stream.write(payload)
                temporaries.append(Path(stream.name))
        for temporary, path in zip(temporaries, paths, strict=True):
            os.replace(temporary, path)
        temporaries.clear()
    except BaseException:
        for path in owned:
            path.unlink(missing_ok=True)
        raise
    finally:
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)
