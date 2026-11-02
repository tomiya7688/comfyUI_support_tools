"""Tests for local capture-set import, evidence routing, and image quality guidance."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from comfyui_support_tools.shared.capture_assistant import (
    CaptureAssistantApplication,
    CaptureFrame,
    CaptureSet,
    CaptureSetImporter,
    register_and_fuse_burst,
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
    #   責務: [_textured_burst:既知の平行移動を持つ合成frame列を生成する]
    #   処理: [repeatable texture and one translated observation for registration checks]
    #   引数: [self: test case]
    #   戻り値: [tuple[Image.Image, ...]: small registered burst]
    # }
    @staticmethod
    def _textured_burst() -> tuple[Image.Image, ...]:
        generator = np.random.default_rng(82)
        reference = generator.integers(20, 235, size=(128, 128, 3), dtype=np.uint8)
        frames = [reference]
        for dx, dy in ((3, -2), (-2, 2)):
            matrix = np.float32([[1, 0, dx], [0, 1, dy]])
            frames.append(cv2.warpAffine(reference, matrix, (128, 128)))
        return tuple(Image.fromarray(frame, "RGB") for frame in frames)

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
    #   責務: [test_burst_registration_fuses_aligned_evidence_and_keeps_fallback: registration acceptanceを検証する]
    #   処理: [align translated frames, assert confidence/count maps and separate candidate provenance]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_burst_registration_fuses_aligned_evidence_and_keeps_fallback(self) -> None:
        frames = self._textured_burst()
        result = register_and_fuse_burst(frames, ("f0", "f1", "f2"), (0.9, 0.8, 0.7))
        self.assertIsNotNone(result.fused_png)
        self.assertEqual(len(result.frame_evidence), 3)
        self.assertGreaterEqual(sum(item.accepted for item in result.frame_evidence), 2)
        self.assertEqual(
            [item[0] for item in result.candidate_images()],
            ["best_single_frame", "multi_frame_fusion"],
        )
        with Image.open(io.BytesIO(result.confidence_map_png)) as confidence:
            self.assertGreater(float(np.asarray(confidence).mean()), 0)
        fused = np.asarray(Image.open(io.BytesIO(result.fused_png)), dtype=np.float32)
        reference = np.asarray(frames[0], dtype=np.float32)
        unaligned_mean = np.mean([np.asarray(frame, dtype=np.float32) for frame in frames], axis=0)
        region = np.s_[12:-12, 12:-12]
        fused_error = np.abs(fused[region] - reference[region]).mean()
        naive_error = np.abs(unaligned_mean[region] - reference[region]).mean()
        self.assertLess(fused_error, naive_error)

    # {
    #   責務: [test_capture_assistant_routes_fused_observation_with_provenance: application integrationを検証する]
    #   処理: [ensure registered burst wins over the former single-frame fallback and is labeled inferred]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_capture_assistant_routes_fused_observation_with_provenance(self) -> None:
        frames = tuple(
            CaptureFrame(
                f"frame-{index}.png",
                self.png(image),
                "image",
                "png",
                f"digest-{index}",
            )
            for index, image in enumerate(self._textured_burst())
        )
        app = CaptureAssistantApplication()
        result = app.process(CaptureSet("burst-integrated", frames), WeakSignalRequest())
        self.assertEqual(result.route, "multi_frame_fusion")
        self.assertIsNotNone(result.multi_frame_fusion.fused_png)
        provenance = result.processing_result.candidates[0].provenance[0]
        self.assertEqual(provenance.kind, EvidenceKind.INFERRED)
        self.assertEqual(provenance.generator, result.multi_frame_fusion.generator)
        manifest = json.loads(app.manifest(result))
        self.assertTrue(manifest["multi_frame_fusion"]["fused"])
        self.assertEqual(len(manifest["multi_frame_fusion"]["frames"]), 3)
        selected_result = app.process(
            CaptureSet("range-selected", frames), WeakSignalRequest(), (1, 3)
        )
        self.assertEqual(
            selected_result.multi_frame_fusion.source_paths, ("frame-1.png", "frame-2.png")
        )
        with self.assertRaisesRegex(ValueError, "frame_range"):
            app.process(CaptureSet("bad-range", frames), WeakSignalRequest(), (2, 5))

    # {
    #   責務: [test_local_video_range_imports_and_fuses_extracted_frames: video input pathを検証する]
    #   処理: [write a tiny local clip, import a selected range, and pass it through registered fusion]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_local_video_range_imports_and_fuses_extracted_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "burst.avi"
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (128, 128))
            if not writer.isOpened():
                self.skipTest("OpenCV MJPG video writer is unavailable")
            try:
                for image in self._textured_burst():
                    writer.write(cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR))
            finally:
                writer.release()
            capture_set = CaptureSetImporter().load_video(path, 0, 3)
            self.assertEqual(len(capture_set.frames), 3)
            self.assertTrue(capture_set.source.startswith("video:burst.avi:"))
            self.assertTrue(capture_set.frames[1].capture_time.startswith("PT"))
            result = CaptureAssistantApplication().process(capture_set, WeakSignalRequest())
            self.assertEqual(result.route, "multi_frame_fusion")

    # {
    #   責務: [test_low_texture_frames_fall_back_without_inventing_fusion: conservative fallbackを検証する]
    #   処理: [reject unobservable blank frames and preserve highest-quality original]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_low_texture_frames_fall_back_without_inventing_fusion(self) -> None:
        frames = (Image.new("RGB", (64, 64), "gray"),) * 3
        result = register_and_fuse_burst(frames, ("a", "b", "c"), (0.4, 0.9, 0.6))
        self.assertIsNone(result.fused_png)
        self.assertEqual(result.warnings, ("insufficient_confident_alignment",))
        with Image.open(io.BytesIO(result.best_frame_png)) as best:
            self.assertEqual(best.getpixel((0, 0)), (128, 128, 128))

    # {
    #   責務: [test_moving_occlusion_is_reported_as_ghosting_risk: motion artifact evidenceを検証する]
    #   処理: [add a moving colored patch and verify pre-flow disagreement remains visible]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_moving_occlusion_is_reported_as_ghosting_risk(self) -> None:
        frames = list(self._textured_burst())
        occluded = frames[0].copy()
        ImageDraw.Draw(occluded).rectangle((35, 35, 85, 85), fill="red")
        frames.append(occluded)
        result = register_and_fuse_burst(
            tuple(frames), ("f0", "f1", "f2", "occluded"), (0.9, 0.8, 0.7, 0.6)
        )
        occlusion_evidence = result.frame_evidence[-1]
        self.assertIn("ghosting_risk", occlusion_evidence.warnings)

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
