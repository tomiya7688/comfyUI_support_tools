from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw

from comfyui_support_tools.shared.pixel_sprite.contracts import (
    SpriteDirection,
    SpriteFrameOrder,
    SpriteFrameSpec,
    SpriteSequenceRequest,
)
from comfyui_support_tools.shared.pixel_sprite.pipeline import (
    SpriteSequenceService,
    apply_shared_palette,
    normalize_to_cell,
    order_frames,
    resolve_layout,
)


# {
# 責務: [PixelSpritePipelineTests: shared-palette/grid/sheet exportを検証する]
# フィールド: [temporary sprite assets]
# 処理: [provider生成、palette固定、layout、animation metadataとreview warningを確認する]
# }
class PixelSpritePipelineTests(unittest.TestCase):
    # {
    # 責務: [setUp: canonical referenceとtest sprite patternを初期化する]
    # 処理: [透明canvas上へpalette anchor colorを描画する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def setUp(self) -> None:
        self.canonical = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        ImageDraw.Draw(self.canonical).rectangle((4, 4, 11, 12), fill=(220, 40, 40, 255))

    # {
    # 責務: [test_generates_four_direction_walk_and_exports_all_artifacts: 4方向walk assetを生成する]
    # 処理: [1: fake frame generatorを使う, 2: PNG/GIF/WebP/JSONとgrid dimensionsを検証する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_generates_four_direction_walk_and_exports_all_artifacts(self) -> None:
        # {
        # 責務: [Generator: test pose patternを返す]
        # フィールド: [call count]
        # 処理: [spec phaseで色を選びpose regionを描く]
        # }
        class Generator:
            # {
            # 責務: [generate: pipeline test用のpose frameを描画する]
            # 処理: [spec indexに応じてsprite patternを少し移動する]
            # 引数: [inner: generator, canonical: anchor, spec: pose spec, prompt: test prompt]
            # 戻り値: [Image: generated RGBA frame]
            # }
            def generate(inner, canonical, spec, prompt):
                image = Image.new("RGBA", (20, 12), (0, 0, 0, 0))
                color = (220, 40, 40, 255) if spec.index % 2 == 0 else (220, 40, 40, 255)
                ImageDraw.Draw(image).rectangle(
                    (6, 2 + spec.index % 2, 13, 9 + spec.index % 2), fill=color
                )
                return image

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "walk_sheet"
            request = SpriteSequenceRequest(
                canonical=self.canonical,
                prompt="red-haired adventurer walking",
                actions=("walk",),
                frames_per_action=3,
                cell_width=16,
                cell_height=16,
                columns=4,
                rows=3,
                margin=1,
                padding=2,
                palette_colors=4,
                export_webp=True,
                output_directory=str(target),
            )
            result = SpriteSequenceService(Generator()).create(request)
            self.assertEqual(result.frame_count, 12)
            self.assertEqual((result.columns, result.rows), (4, 3))
            with Image.open(result.sprite_sheet) as sheet:
                self.assertEqual(sheet.size, (72, 54))
            self.assertTrue(Path(result.gif_path).is_file())
            self.assertTrue(Path(result.webp_path).is_file())
            self.assertEqual(len(list(Path(result.frames_directory).glob("*.png"))), 12)
            metadata = json.loads(Path(result.metadata_path).read_text(encoding="utf-8"))
            self.assertEqual(metadata["frames"][0]["direction"], "front")
            self.assertEqual(metadata["palette"]["source"], "canonical_sprite")
            self.assertTrue(
                any("No identity/shape evaluator" in warning for warning in result.warnings)
            )
            repack_target = Path(temporary) / "repacked"
            edited = list(result.frames)
            edited[0] = type(edited[0])(
                edited[0].spec, Image.new("RGBA", (9, 17), (30, 220, 30, 255))
            )
            repacked = SpriteSequenceService().repack(
                replace(
                    request,
                    output_directory=str(repack_target),
                    export_gif=False,
                    export_webp=False,
                ),
                tuple(edited),
            )
            self.assertEqual(repacked.frame_count, 12)
            self.assertTrue(Path(repacked.sprite_sheet).is_file())

    # {
    # 責務: [test_shared_palette_and_nearest_grid_are_deterministic: palette/grid normalizationを検証する]
    # 処理: [1: nearest resizeしてcellへ収める, 2: palette anchor以外の色が出ないことを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_shared_palette_and_nearest_grid_are_deterministic(self) -> None:
        source = Image.new("RGBA", (3, 2), (0, 0, 0, 0))
        source.putpixel((0, 0), (220, 40, 40, 255))
        fitted = normalize_to_cell(source, 16, 16)
        self.assertEqual(fitted.size, (16, 16))
        palette = self.canonical.convert("RGB").quantize(colors=4)
        output = apply_shared_palette(fitted, palette)
        self.assertEqual(output.getpixel((0, 0))[3], 0)
        used = {pixel[:3] for pixel in output.getdata() if pixel[3]}
        allowed = {tuple(palette.getpalette()[index : index + 3]) for index in range(0, 12, 3)}
        self.assertLessEqual(used, allowed)

    # {
    # 責務: [test_canonical_front_idle_frame_is_preserved_without_generation_backend: canonical anchor frameを維持する]
    # 処理: [1: single-front-idle sequenceを生成する, 2: providerなしでcanonicalをそのまま採用する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_canonical_front_idle_frame_is_preserved_without_generation_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            request = SpriteSequenceRequest(
                canonical=self.canonical,
                prompt="canonical character",
                directions=(SpriteDirection.FRONT,),
                actions=("idle",),
                frames_per_action=1,
                cell_width=16,
                cell_height=16,
                output_directory=str(Path(temporary) / "idle"),
                export_gif=False,
            )
            result = SpriteSequenceService().create(request)
            self.assertEqual(result.frame_count, 1)
            self.assertEqual(result.frames[0].image.getpixel((7, 8)), (220, 40, 40, 255))

    # {
    # 責務: [test_frame_order_uses_compass_order_and_layout_fills_requested_grid: layout orderを保証する]
    # 処理: [1: shuffled frame specsをdirection-majorへsortする, 2: partial grid dimensionを解決する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_frame_order_uses_compass_order_and_layout_fills_requested_grid(self) -> None:
        from comfyui_support_tools.shared.pixel_sprite.contracts import SpriteFrame

        specs = (
            SpriteFrameSpec("idle", SpriteDirection.RIGHT, 0, 1, 0),
            SpriteFrameSpec("idle", SpriteDirection.FRONT, 0, 1, 0),
        )
        frames = tuple(SpriteFrame(spec, self.canonical.copy()) for spec in specs)
        ordered = order_frames(frames, SpriteFrameOrder.DIRECTION_MAJOR)
        self.assertEqual(ordered[0].spec.direction, SpriteDirection.FRONT)
        self.assertEqual(resolve_layout(10, columns=4, rows=0), (4, 3))

    # {
    # 責務: [test_provider_metrics_are_checked_and_existing_output_is_not_overwritten: evaluator境界を検証する]
    # 処理: [1: invalid scoreを返すproviderを実行する, 2: existing outputへの上書きを拒否する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_provider_metrics_are_checked_and_existing_output_is_not_overwritten(self) -> None:
        # {
        # 責務: [Generator: pixel sprite pipelineのdomain責務を提供する]
        # フィールド: [sequence contractまたはservice dependencies]
        # 処理: [canonical anchorから安全なsprite assetsを構成する]
        # }
        class Generator:
            # {
            # 責務: [generate: pixel sprite assetsの処理または検証を行う]
            # 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
            # 引数: [self, canonical, spec, prompt]
            # 戻り値: [sprite処理結果]
            # }
            def generate(self, canonical, spec, prompt):
                return canonical

        # {
        # 責務: [Evaluator: pixel sprite pipelineのdomain責務を提供する]
        # フィールド: [sequence contractまたはservice dependencies]
        # 処理: [canonical anchorから安全なsprite assetsを構成する]
        # }
        class Evaluator:
            # {
            # 責務: [evaluate: pixel sprite assetsの処理または検証を行う]
            # 処理: [1: pose/image/layoutを検証する, 2: bounded outputを返す]
            # 引数: [self, canonical, frame, spec]
            # 戻り値: [sprite処理結果]
            # }
            def evaluate(self, canonical, frame, spec):
                return {"identity": 1.2, "shape": 0.9, "palette": 1.0}

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "assets"
            request = SpriteSequenceRequest(
                self.canonical,
                "sprite",
                directions=(SpriteDirection.FRONT,),
                cell_width=16,
                cell_height=16,
                output_directory=str(target),
                export_gif=False,
            )
            with self.assertRaisesRegex(ValueError, "identity score"):
                SpriteSequenceService(Generator(), Evaluator()).create(request)
            target.mkdir()
            with self.assertRaises(FileExistsError):
                SpriteSequenceService(Generator()).create(request)


if __name__ == "__main__":
    unittest.main()
