"""Shared Pixel Art Creator workflow, grid, evaluator, editor, and persistence tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from comfyui_support_tools.shared.pixel_art import (
    SIZE_PRESETS,
    PixelArtApplication,
    PixelArtRequest,
    PixelArtSettings,
    PixelEdit,
    PixelTextBackend,
    combine_sprite_sheet,
    from_grid,
    nearest_preview,
    split_sprite_sheet,
    to_grid,
)


# {
# 責務: [FakePixelTextBackend: text workflowに再現可能なdraftを返す]
# フィールド: [draft: fixed source candidate]
# 処理: [external generation runtimeを使わずbackend contractを検証する]
# }
class FakePixelTextBackend(PixelTextBackend):
    # {
    # 責務: [__init__: fake candidateを保持する]
    # 処理: [same deterministic image for every test call]
    # 引数: [draft: backend candidate image]
    # 戻り値: [None: initialized fake backend]
    # }
    def __init__(self, draft: Image.Image):
        self.draft = draft
        self.request = None

    # {
    # 責務: [generate: satisfy text backend protocol]
    # 処理: [record request and return repeatable candidate tuple]
    # 引数: [request: PixelArtRequest]
    # 戻り値: [tuple[Image, ...]: generated draft candidates]
    # }
    def generate(self, request: PixelArtRequest) -> tuple[Image.Image, ...]:
        self.request = request
        return (self.draft.copy(), self.draft.copy())


# {
# 責務: [PixelArtCreatorTests: exercise shared app contracts and edge cases]
# フィールド: [temporary paths and source grid fixtures]
# 処理: [test all three workflows, deterministic quality pipeline, and persisted history]
# }
class PixelArtCreatorTests(unittest.TestCase):
    # {
    # 責務: [test_all_presets_create_strict_grid_and_nearest_preview: check supported dimensions]
    # 処理: [run all documented size presets and verify exact integer upscale]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_all_presets_create_strict_grid_and_nearest_preview(self):
        source = Image.new("RGBA", (24, 16), (200, 50, 80, 255))
        for size in SIZE_PRESETS:
            result = PixelArtApplication().image_to_pixel(
                source, PixelArtSettings(size=size, color_count=8)
            )
            self.assertEqual((result.grid.width, result.grid.height), (size, size))
            self.assertEqual(result.preview.size, (size * 8, size * 8))
            self.assertLessEqual(dict(result.metric.counts)["color_count"], 9)

    # {
    # 責務: [test_custom_palette_alpha_and_crop_policy_are_shared: validate palette and alpha behavior]
    # 処理: [convert to fixed palette with transparent padding and preserve native alpha]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_custom_palette_alpha_and_crop_policy_are_shared(self):
        source = Image.new("RGBA", (4, 2), (250, 0, 0, 128))
        settings = PixelArtSettings(
            custom_size=(8, 8),
            palette_mode="custom",
            palette=((0, 0, 0, 255), (255, 0, 0, 255)),
            crop_policy="transparent_pad",
        )
        result = PixelArtApplication().image_to_pixel(source, settings)
        self.assertEqual((result.grid.width, result.grid.height), (8, 8))
        self.assertIn((255, 0, 0, 128), result.grid.pixels)
        self.assertIn((0, 0, 0, 0), result.grid.pixels)
        self.assertEqual(len(set(result.grid.pixels)), 2)

    # {
    # 責務: [test_text_and_image_entrypoints_return_ranked_shared_results: validate text route]
    # 処理: [backend candidates pass through strict-grid rendering and common evaluator]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_text_and_image_entrypoints_return_ranked_shared_results(self):
        backend = FakePixelTextBackend(Image.new("RGBA", (20, 10), (30, 120, 240, 255)))
        application = PixelArtApplication(backend)
        request = PixelArtRequest("blue potion icon", PixelArtSettings(size=16), candidate_count=2)
        results = application.text_to_pixel(request)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].metadata["workflow"], "text")
        self.assertIs(backend.request, request)
        image_result = application.image_to_pixel(backend.draft, request.settings, mode="icon")
        self.assertEqual(image_result.grid.width, 16)
        with self.assertRaises(RuntimeError):
            PixelArtApplication().text_to_pixel(request)

    # {
    # 責務: [test_pixel_edits_are_reversible_and_project_history_survives_reload: edit and save history]
    # 処理: [pencil, fill, undo/redo, snapshot save, and project load]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_pixel_edits_are_reversible_and_project_history_survives_reload(self):
        app = PixelArtApplication()
        source = app.image_to_pixel(
            Image.new("RGBA", (8, 8), (0, 0, 0, 0)), PixelArtSettings(size=8)
        )
        project = app.new_project(source)
        edited = project.apply((PixelEdit("pencil", 0, 0, (255, 10, 10, 255)),))
        self.assertEqual(from_grid(edited).getpixel((0, 0)), (255, 10, 10, 255))
        self.assertEqual(project.undo().pixels, source.grid.pixels)
        self.assertEqual(project.redo().pixels, edited.pixels)
        replacement = PixelArtApplication().retouch(edited, (PixelEdit("eraser", 0, 0),)).grid
        project.apply_grid(replacement)
        self.assertEqual(project.grid.pixels[0], (0, 0, 0, 0))
        self.assertEqual(project.undo().pixels, edited.pixels)
        with self.assertRaises(ValueError):
            project.apply_grid(to_grid(Image.new("RGBA", (2, 2))))
        with tempfile.TemporaryDirectory() as temporary:
            saved = project.save(Path(temporary) / "potion-project")
            loaded = type(project).load(saved)
            self.assertEqual(loaded.grid.pixels, edited.pixels)
            self.assertTrue(loaded.can_undo)
            self.assertEqual(json.loads((saved / "project.json").read_text())["snapshots"], 3)

    # {
    # 責務: [test_palette_replace_cleanup_and_native_zoom_keep_exact_grid: validate retouch tools]
    # 処理: [replace palette colors, clean isolated pixel, and ensure nearest scaled cells]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_palette_replace_cleanup_and_native_zoom_keep_exact_grid(self):
        image = Image.new("RGBA", (5, 5), (20, 20, 20, 255))
        image.putpixel((2, 2), (250, 0, 0, 255))
        grid = to_grid(image)
        app = PixelArtApplication()
        result = app.retouch(
            grid,
            (PixelEdit("replace_color", color=(0, 200, 0, 255), source_color=(250, 0, 0, 255)),),
        )
        self.assertEqual(result.grid.pixels[12], (0, 200, 0, 255))
        cleanup = app.retouch(grid, (PixelEdit("cleanup_islands"),))
        self.assertEqual(cleanup.grid.pixels[12], (20, 20, 20, 255))
        preview = nearest_preview(result.grid, 4)
        self.assertEqual(preview.getpixel((0, 0)), result.grid.pixels[0])
        self.assertEqual(preview.getpixel((1, 1)), result.grid.pixels[0])
        candidates = app.cleanup_candidates(grid)
        self.assertEqual(
            tuple(mode for mode, _ in candidates), ("conservative", "standard", "aggressive")
        )
        self.assertEqual(candidates[0][1].metadata["changed_pixels"], 1)
        self.assertEqual(candidates[0][1].metadata["changed_regions"], ((2, 2, 3, 3),))
        self.assertIsNone(candidates[0][1].metadata["semantic_confidence"])

    # {
    # 責務: [test_palette_and_alpha_cleanup_are_explicit_and_bounded: cover focused pixel retouch APIs]
    # 処理: [replace palette colors and remove partial alpha without changing grid dimensions]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_palette_and_alpha_cleanup_are_explicit_and_bounded(self):
        image = Image.new("RGBA", (3, 1), (200, 20, 10, 255))
        image.putpixel((1, 0), (10, 20, 30, 64))
        image.putpixel((2, 0), (10, 20, 30, 192))
        grid = to_grid(image)
        app = PixelArtApplication()
        replaced = app.replace_palette_color(grid, (200, 20, 10, 255), (0, 0, 0, 255))
        self.assertEqual(replaced.grid.pixels[0], (0, 0, 0, 255))
        cleaned = app.cleanup_transparent_edges(grid, threshold=128)
        self.assertEqual(cleaned.grid.pixels[1], (10, 20, 30, 0))
        self.assertEqual(cleaned.grid.pixels[2], (10, 20, 30, 255))
        reduced = app.reduce_palette(grid, 1)
        self.assertEqual((reduced.grid.width, reduced.grid.height), (3, 1))
        with self.assertRaises(ValueError):
            app.cleanup_transparent_edges(grid, threshold=0)

    # {
    # 責務: [test_export_is_no_clobber_and_sprite_sheet_cells_roundtrip: exercise export and atlas]
    # 処理: [export transparent result, check palette metadata and combine/split cells]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_export_is_no_clobber_and_sprite_sheet_cells_roundtrip(self):
        app = PixelArtApplication()
        result = app.image_to_pixel(
            Image.new("RGBA", (8, 8), (90, 30, 10, 255)), PixelArtSettings(size=8)
        )
        with tempfile.TemporaryDirectory() as temporary:
            paths = app.export(result, Path(temporary), "asset")
            self.assertTrue(paths[0].is_file())
            self.assertEqual(json.loads(paths[1].read_text())["colors_rgba"], [[90, 30, 10, 255]])
            with self.assertRaises(FileExistsError):
                app.export(result, Path(temporary), "asset")
        source = Image.new("RGBA", (4, 2), (0, 0, 0, 0))
        source.putpixel((0, 0), (255, 0, 0, 255))
        frames = split_sprite_sheet(source, 2, 2)
        atlas = combine_sprite_sheet(frames, columns=2)
        self.assertEqual(atlas.size, source.size)
        self.assertEqual(split_sprite_sheet(atlas, 2, 2), frames)
        palette = app.extract_palette(source, 2)
        self.assertTrue(palette)
        with tempfile.TemporaryDirectory() as temporary:
            palette_path = Path(temporary) / "palette.json"
            palette_path.write_text(json.dumps({"colors_rgba": [list(color) for color in palette]}))
            from comfyui_support_tools.shared.pixel_art import load_palette

            self.assertEqual(load_palette(palette_path), palette)

    # {
    # 責務: [test_invalid_settings_operations_and_candidate_counts_fail_early: reject invalid API use]
    # 処理: [validate size, editor operation, and candidate count boundaries]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_invalid_settings_operations_and_candidate_counts_fail_early(self):
        with self.assertRaises(ValueError):
            PixelArtApplication().image_to_pixel(
                Image.new("RGB", (2, 2)), PixelArtSettings(size=12)
            )
        with self.assertRaises(ValueError):
            PixelArtApplication().retouch(
                to_grid(Image.new("RGBA", (2, 2))), (PixelEdit("erase", 0, 0),)
            )
        with self.assertRaises(ValueError):
            PixelArtApplication(FakePixelTextBackend(Image.new("RGB", (1, 1)))).text_to_pixel(
                PixelArtRequest("x", candidate_count=17)
            )


if __name__ == "__main__":
    unittest.main()
