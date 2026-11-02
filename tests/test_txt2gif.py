"""Tests for loop motion, palette encoding, size budgets and backend contracts."""

from __future__ import annotations

import io
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from PIL import Image

from comfyui_support_tools.shared.txt2gif import (
    AnimationBackendRegistry,
    AnimationLayer,
    DitherMode,
    MotionKind,
    Txt2GifApplication,
    Txt2GifRequest,
    encode_gif,
    render_key_art_loop,
    seal_loop,
)


# {
#   責務: [Txt2GifTests: still-first loop rendering and GIF output guaranteesを検証する]
#   フィールド: [Pillow fixtures, per-region animation layer, temporary destinations]
#   処理: [exact loop seam, static background, common palette, size limit and service callbacksを確認する]
# }
class Txt2GifTests(unittest.TestCase):
    # {
    #   責務: [setUp: 128px canvas requestと周期motion fixtureを作成する]
    #   処理: [initialize clean plate and one localized red subject layer]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def setUp(self) -> None:
        self.clean_plate = Image.new("RGBA", (128, 128), (20, 40, 60, 255))
        layer = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        for y in range(48, 80):
            for x in range(48, 80):
                layer.putpixel((x, y), (240, 40, 30, 255))
        self.layer = AnimationLayer(
            "hair tips",
            _png_bytes(layer),
            amplitude_x=4,
            amplitude_y=0,
            kind=MotionKind.HAIR_SWAY,
        )
        self.request = Txt2GifRequest(
            "anime character with wind-swept hair",
            Path("loop.gif"),
            width=128,
            height=128,
            frame_count=16,
            minimum_dimension=128,
        )

    # {
    #   責務: [test_key_art_loop_moves_only_region_and_closes_exactly: periodic local motion keeps background still]
    #   処理: [render frames from clean plate and compare static pixel and first/last frame values]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_key_art_loop_moves_only_region_and_closes_exactly(self) -> None:
        frames = render_key_art_loop(_png_bytes(self.clean_plate), (self.layer,), self.request)
        self.assertEqual(len(frames), 16)
        self.assertEqual(frames[0].tobytes(), frames[-1].tobytes())
        self.assertEqual(frames[0].getpixel((8, 8)), self.clean_plate.getpixel((8, 8)))
        self.assertNotEqual(frames[4].getpixel((83, 64)), frames[0].getpixel((83, 64)))
        sealed = seal_loop(frames[:-1] + (frames[-2],))
        self.assertEqual(sealed[0].tobytes(), sealed[-1].tobytes())

    # {
    #   責務: [test_encoder_emits_optimized_global_palette_gif: GIF settings and sidecar metrics are respected]
    #   処理: [encode periodic frames and inspect GIF timing, looping, palette and reported seam]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_encoder_emits_optimized_global_palette_gif(self) -> None:
        frames = render_key_art_loop(_png_bytes(self.clean_plate), (self.layer,), self.request)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "anime-loop.gif"
            result = encode_gif(
                frames, replace(self.request, output_path=path, dither=DitherMode.NONE)
            )
            self.assertTrue(path.is_file())
            self.assertLessEqual(result.file_bytes, 8_000_000)
            self.assertEqual(result.seam_error, 0)
            with Image.open(path) as gif:
                self.assertEqual(gif.format, "GIF")
                self.assertEqual(gif.info["loop"], 0)
                self.assertEqual(gif.info["duration"], 120)
                self.assertLessEqual(len(gif.getpalette()), 768)

    # {
    #   責務: [test_size_budget_failure_does_not_leave_partial_output: impossible budgets fail atomically]
    #   処理: [force every palette/dimension option over budget and assert no destination was committed]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_size_budget_failure_does_not_leave_partial_output(self) -> None:
        frames = render_key_art_loop(_png_bytes(self.clean_plate), (self.layer,), self.request)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "too-large.gif"
            request = Txt2GifRequest(
                "anime",
                path,
                width=128,
                height=128,
                frame_count=16,
                maximum_file_bytes=64,
                minimum_dimension=128,
            )
            with self.assertRaisesRegex(ValueError, "size budget"):
                encode_gif(frames, request)
            self.assertFalse(path.exists())

    # {
    #   責務: [test_backend_contract_runs_canonical_art_and_layer_extraction_once: injected adapter orchestration is deterministic]
    #   処理: [verify still generation, layer extraction, progress and file output sequence]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_backend_contract_runs_canonical_art_and_layer_extraction_once(self) -> None:
        # {
        #   責務: [FakeBackend: still generation and mask extraction fixture]
        #   フィールド: [clean plate and one isolated animation layer]
        # }
        class FakeBackend:
            # {
            #   責務: [generate_still: one canonical still fixtureを生成する]
            #   処理: [return request-sized PNG reference art]
            #   引数: [self: fake adapter, request: generation settings]
            #   戻り値: [bytes: canonical PNG still]
            # }
            def generate_still(self, request):
                return _png_bytes(Image.new("RGBA", (request.width, request.height), "red"))

            # {
            #   責務: [extract_layers: inpainted plate and isolated subject layerを返す]
            #   処理: [use prepared fixture data as segmentation/backend output]
            #   引数: [self: fake adapter, still_png: canonical still, request: motion request]
            #   戻り値: [tuple: clean plate PNG and RGBA motion layers]
            # }
            def extract_layers(self, still_png, request):
                return _png_bytes(self_outer.clean_plate), (self_outer.layer,)

        self_outer = self
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "result.gif"
            request = Txt2GifRequest(
                "anime idle loop",
                output_path,
                width=128,
                height=128,
                frame_count=8,
                minimum_dimension=128,
            )
            events = []
            backend = FakeBackend()
            registry = AnimationBackendRegistry((("key_art", backend),))
            result = Txt2GifApplication(registry).generate(
                request, "KEY_ART", progress=events.append
            )
            self.assertTrue(output_path.exists())
            self.assertEqual(result.path, output_path)
            self.assertEqual(len(events), 3)
            self.assertEqual(registry.backend_ids, ("key_art",))
            with self.assertRaisesRegex(ValueError, "already registered"):
                registry.register("KEY_ART", backend)
            with self.assertRaisesRegex(LookupError, "not registered"):
                registry.get("unknown")

    # {
    #   責務: [test_request_rejects_long_video_profiles: Txt2GIF is bounded to short loop use]
    #   処理: [reject invalid cadence, frame count, color budget and canvas constraints]
    #   引数: [self: test case]
    #   戻り値: []
    # }
    def test_request_rejects_long_video_profiles(self) -> None:
        with self.assertRaises(ValueError):
            Txt2GifRequest("anime", Path("x.gif"), fps=30)
        with self.assertRaises(ValueError):
            Txt2GifRequest("anime", Path("x.gif"), frame_count=100)
        with self.assertRaises(ValueError):
            Txt2GifRequest("anime", Path("x.gif"), color_count=512)
        with self.assertRaisesRegex(ValueError, "total frame budget"):
            Txt2GifRequest("anime", Path("x.gif"), width=1024, height=1024, frame_count=48)


# {
#   責務: [_png_bytes: encode an in-memory RGBA fixture as a PNG]
#   処理: [serialize a PIL image without writing a test artifact to disk]
#   引数: [image: source RGBA fixture]
#   戻り値: [bytes: encoded PNG]
# }
def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
