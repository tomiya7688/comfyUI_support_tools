"""Tests for local capture-set import, evidence routing, and image quality guidance."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from comfyui_support_tools.shared.capture_assistant import (
    CaptureAssistantApplication,
    CaptureFrame,
    CaptureSet,
    CaptureSetImporter,
)
from comfyui_support_tools.shared.weak_signal import (
    EvidenceKind,
    WeakSignalMode,
    WeakSignalRequest,
)


# {
#   責務: [CaptureAssistantTests: import, exposure bracket, RAW, quality and fallbackを検証する]
#   フィールド: [small locally generated RGB/RAW test fixtures]
#   処理: [exercise each optional capture capability without hardware or network]
# }
class CaptureAssistantTests(unittest.TestCase):
    # {
    #   責務: [png: RGB image fixtureをPNG bytesへ変換する]
    #   処理: [create deterministic local test payload]
    #   引数: [image: RGB source]
    #   戻り値: [bytes: encoded PNG]
    # }
    @staticmethod
    def png(image: Image.Image) -> bytes:
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        return stream.getvalue()

    # {
    #   責務: [test_importer_reads_exposure_metadata_and_hashes: manifest observationsを検証する]
    #   処理: [load local burst and preserve per-frame exposure metadata/digests]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_importer_reads_exposure_metadata_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "low.png").write_bytes(self.png(Image.new("RGB", (12, 12), 50)))
            (root / "high.png").write_bytes(self.png(Image.new("RGB", (12, 12), 100)))
            (root / "capture-set.json").write_text(
                json.dumps(
                    {
                        "schema": "capture-set.v1",
                        "capture_set_id": "bracket-1",
                        "aligned_frames_assumed": True,
                        "frames": [
                            {"path": "low.png", "exposure_ev": -1, "iso": 100},
                            {"path": "high.png", "exposure_ev": 1, "iso": 100},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            capture_set = CaptureSetImporter().load(root)
        self.assertTrue(capture_set.has_exposure_bracket)
        self.assertTrue(capture_set.aligned_frames_assumed)
        self.assertEqual({frame.iso for frame in capture_set.frames}, {100})
        self.assertTrue(all(len(frame.sha256) == 64 for frame in capture_set.frames))

    # {
    #   責務: [test_manifest_rejects_path_traversal: manifest path escapeを防ぐ]
    #   処理: [reject parent path before reading outside the selected capture folder]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_manifest_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "capture-set.json").write_text(
                json.dumps({"schema": "capture-set.v1", "frames": [{"path": "../secret.jpg"}]}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "local file names"):
                CaptureSetImporter().load(root)

    # {
    #   責務: [test_quality_score_flags_blurred_frame: blur and clipping guidanceを検証する]
    #   処理: [compare a high-detail target against a blurred rendering]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_quality_score_flags_blurred_frame(self) -> None:
        sharp = Image.new("RGB", (64, 64), "white")
        draw = ImageDraw.Draw(sharp)
        for x in range(0, 64, 8):
            draw.rectangle((x, 0, x + 3, 63), fill="black")
        blurred = sharp.filter(ImageFilter.GaussianBlur(3))
        frames = (
            CaptureFrame("sharp.png", self.png(sharp), "image", "png", "1"),
            CaptureFrame("blur.png", self.png(blurred), "image", "png", "2"),
        )
        result = CaptureAssistantApplication().process(
            CaptureSet("quality", frames),
            WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL),
        )
        self.assertGreater(result.quality[0].blur_proxy, result.quality[1].blur_proxy)
        self.assertEqual(result.route, "weak_signal_multiframe")

    # {
    #   責務: [test_duplicate_frames_warn_about_capture_diversity: viewpoint不足の事後guidanceを検証する]
    #   処理: [confirm identical observations produce a low inter-frame difference warning]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_duplicate_frames_warn_about_capture_diversity(self) -> None:
        encoded = self.png(Image.new("RGB", (8, 8), "gray"))
        frames = tuple(
            CaptureFrame(f"frame-{index}.png", encoded, "image", "png", str(index))
            for index in range(2)
        )
        result = CaptureAssistantApplication().process(
            CaptureSet("duplicates", frames),
            WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL),
        )
        self.assertEqual(result.interframe_difference_proxy, 0.0)
        self.assertIn("low_interframe_difference_check_capture_diversity", result.guidance)

    # {
    #   責務: [test_unaligned_burst_uses_best_single_frame_fallback: misaligned burst safetyを検証する]
    #   処理: [auto mode must avoid cross-frame layer separation without declared alignment]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_unaligned_burst_uses_best_single_frame_fallback(self) -> None:
        frames = tuple(
            CaptureFrame(
                f"frame-{index}.png",
                self.png(Image.new("RGB", (8, 8), color)),
                "image",
                "png",
                str(index),
            )
            for index, color in enumerate(("gray", "white", "black"))
        )
        result = CaptureAssistantApplication().process(
            CaptureSet("unaligned", frames), WeakSignalRequest()
        )
        self.assertEqual(result.route, "single_image_fallback:unaligned_burst")
        self.assertEqual(len(result.processing_result.candidates[0].frames), 1)

    # {
    #   責務: [test_exposure_bracket_fuses_and_marks_input_inferred: bracket合成来歴を検証する]
    #   処理: [merge two EV-separated local images and carry fusion provenance into candidate metadata]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_exposure_bracket_fuses_and_marks_input_inferred(self) -> None:
        frames = (
            CaptureFrame(
                "dark.png",
                self.png(Image.new("RGB", (16, 16), 40)),
                "image",
                "png",
                "a",
                exposure_ev=-1,
            ),
            CaptureFrame(
                "bright.png",
                self.png(Image.new("RGB", (16, 16), 80)),
                "image",
                "png",
                "b",
                exposure_ev=1,
            ),
        )
        result = CaptureAssistantApplication().process(
            CaptureSet("bracket", frames),
            WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL),
        )
        self.assertIsNotNone(result.exposure_fusion)
        self.assertEqual(result.exposure_fusion.source_paths, ("dark.png", "bright.png"))
        self.assertEqual(
            result.processing_result.candidates[0].provenance[0].kind,
            EvidenceKind.INFERRED,
        )
        sidecar = json.loads(CaptureAssistantApplication().manifest(result))
        self.assertEqual(sidecar["privacy"], "local_only")
        self.assertEqual(sidecar["exposure_fusion"]["generator"], "exposure_normalized_mean_v1")

    # {
    #   責務: [test_single_image_is_generic_fallback_and_polarization_fallback_is_visible: compatibility fallbackを検証する]
    #   処理: [run a single observation without specialized hardware/backend]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_single_image_is_generic_fallback(self) -> None:
        frame = CaptureFrame(
            "single.png", self.png(Image.new("RGB", (8, 8), "gray")), "image", "png", "a"
        )
        result = CaptureAssistantApplication().process(
            CaptureSet("single", (frame,)),
            WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL),
        )
        self.assertEqual(result.route, "single_image_fallback")
        self.assertEqual(len(result.processing_result.candidates[0].frames), 1)

    # {
    #   責務: [test_raw_frame_is_preserved_without_decoder_and_processed_with_adapter: optional RAW pathを検証する]
    #   処理: [ensure unavailable rawpy does not block import and injected decoders enable processing]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_raw_frame_requires_optional_decoder_for_processing(self) -> None:
        frame = CaptureFrame("raw.dng", b"raw payload", "raw", "dng", "digest")
        with self.assertRaisesRegex(RuntimeError, "requires a configured decoder"):
            CaptureAssistantApplication().process(
                CaptureSet("raw", (frame,)),
                WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL),
            )

        # {
        #   責務: [FakeRawDecoder: test内の注入RAW adapterを表す]
        #   フィールド: [expected payload]
        #   処理: [return deterministic RGB pixels without an optional package]
        # }
        class FakeRawDecoder:
            # {
            #   責務: [decode_rgb: deterministic RAW fixtureをPillow pixelsへ変換する]
            #   処理: [exercise the injected optional decoder boundary]
            #   引数: [payload: retained RAW bytes]
            #   戻り値: [Image.Image: decoded fixture]
            # }
            def decode_rgb(self, payload: bytes) -> Image.Image:
                if payload != b"raw payload":
                    raise ValueError("unexpected raw test payload")
                return Image.new("RGB", (8, 8), 90)

        processed = CaptureAssistantApplication(raw_decoder=FakeRawDecoder()).process(
            CaptureSet("raw", (frame,)),
            WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL),
        )
        self.assertEqual(processed.capture_set.frames[0].payload, b"raw payload")

    # {
    #   責務: [test_polarization_backend_is_selected_when_capable: specialized routeを検証する]
    #   処理: [provide backend plugin accepting polarization metadata and assert it handles the original set]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_polarization_backend_is_selected_when_capable(self) -> None:
        # {
        #   責務: [TestPolarizationBackend: plugin contract selectionを検証する]
        #   フィールド: [stable test route name]
        #   処理: [claim only capture sets that include polarization angles]
        # }
        class TestPolarizationBackend:
            name = "polarized_test_backend"

            # {
            #   責務: [supports: test backend capability checkを行う]
            #   処理: [select only polarized observations]
            #   引数: [capture_set: original test observations]
            #   戻り値: [bool: whether a polarization cue exists]
            # }
            def supports(self, capture_set: CaptureSet) -> bool:
                return capture_set.has_polarization

            # {
            #   責務: [process: specialized backend test doubleでcandidate resultを返す]
            #   処理: [delegate a copy of one frame through the generic local path]
            #   引数: [capture_set: original observations, request: downstream task, fusion: optional EV fusion]
            #   戻り値: [WeakSignalResult: test result]
            # }
            def process(self, capture_set, request, fusion):
                return (
                    CaptureAssistantApplication()
                    .process(
                        CaptureSet(capture_set.capture_set_id, (capture_set.frames[0],)),
                        WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL),
                    )
                    .processing_result
                )

        frames = tuple(
            CaptureFrame(
                f"pol-{angle}.png",
                self.png(Image.new("RGB", (8, 8), 70)),
                "image",
                "png",
                str(angle),
                polarization_angle=angle,
            )
            for angle in (0, 45, 90, 135)
        )
        result = CaptureAssistantApplication(backends=(TestPolarizationBackend(),)).process(
            CaptureSet("polarized", frames),
            WeakSignalRequest(mode=WeakSignalMode.WEAK_DETAIL),
        )
        self.assertEqual(result.route, "polarized_test_backend")


if __name__ == "__main__":
    unittest.main()
