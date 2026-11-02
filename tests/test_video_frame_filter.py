"""Synthetic-frame tests for the low-information filter decision boundary."""

from __future__ import annotations

import unittest

import numpy as np

from comfyui_support_tools.shared.contracts.frame_analysis import (
    DecodedVideoFrame,
    FrameDecodeStatus,
)
from comfyui_support_tools.shared.contracts.frame_filter import (
    FrameFilterAction,
    FrameFilterDecision,
    FrameFilterOptions,
    FrameFilterPreset,
    FrameTextBox,
)
from comfyui_support_tools.shared.video_frame_filter import analyze_frame_sequence
from comfyui_support_tools.shared.video_frame_normalization import normalize_decoded_frame


# {
#   責務: [VideoFrameFilterTests: low-information evidenceとfalse-drop protectionを検証する]
#   フィールド: [synthetic normalized frame fixtures]
# }
class VideoFrameFilterTests(unittest.TestCase):
    # {
    #   責務: [_frame: synthetic RGB pixelsをcommon analysis contractへ正規化する]
    #   処理: [1: pixelsを用意する 2: metadata付きDecodedVideoFrameをnormalizeする]
    #   引数: [pixels: RGB uint8 image]
    #   戻り値: [normalized FrameAnalysisInput]
    # }
    def _frame(self, pixels: np.ndarray):
        return normalize_decoded_frame(
            DecodedVideoFrame(
                pixels,
                "rgb24",
                actual_timestamp=0.0,
            )
        )

    # {
    #   責務: [test_blank_extremes_drop_but_dark_detail_is_kept: blank black/whiteを落とし暗い構造を保護する]
    #   処理: [1: blank extremesとdark sceneを作る 2: decisionsを比較する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_blank_extremes_drop_but_dark_detail_is_kept(self) -> None:
        black = self._frame(np.zeros((48, 48, 3), dtype=np.uint8))
        white = self._frame(np.full((48, 48, 3), 255, dtype=np.uint8))
        rng = np.random.default_rng(423)
        night = self._frame(rng.integers(12, 48, size=(48, 48, 3), dtype=np.uint8))
        options = FrameFilterOptions(
            enabled=True,
            preset=FrameFilterPreset.BALANCED,
            detect_text_only=False,
            detect_title_credits=False,
        )

        result = analyze_frame_sequence("scene", (black, white, night), options)

        self.assertEqual(result.reports[0].decision, FrameFilterDecision.DROP)
        self.assertEqual(result.reports[1].decision, FrameFilterDecision.DROP)
        self.assertEqual(result.reports[2].decision, FrameFilterDecision.KEEP)
        self.assertIn("near_black_low_structure", result.reports[0].reasons)
        self.assertEqual((result.kept_count, result.dropped_count), (1, 2))

    # {
    #   責務: [test_visual_subject_and_regular_subtitle_are_kept: white backgroundや字幕付き映像のfalse dropを防ぐ]
    #   処理: [1: edge-rich white sceneとtext-box付きsceneを作る 2: keep decisionを検証する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_visual_subject_and_regular_subtitle_are_kept(self) -> None:
        white_canvas = np.full((48, 48, 3), 255, dtype=np.uint8)
        white_canvas[12:36, 14:34] = 30
        white_scene = self._frame(white_canvas)
        rng = np.random.default_rng(29)
        footage = self._frame(rng.integers(35, 220, size=(48, 48, 3), dtype=np.uint8))
        options = FrameFilterOptions(enabled=True, preset=FrameFilterPreset.AGGRESSIVE)
        boxes = {1: (FrameTextBox(0.2, 0.88, 0.6, 0.06, text="subtitle"),)}

        result = analyze_frame_sequence(
            "footage", (white_scene, footage), options, text_boxes=boxes
        )

        self.assertEqual(result.reports[0].decision, FrameFilterDecision.KEEP)
        self.assertEqual(result.reports[1].decision, FrameFilterDecision.KEEP)
        self.assertNotIn("text_only_low_visual_information", result.reports[1].reasons)

    # {
    #   責務: [test_text_only_and_title_policies: OCR evidenceが背景情報と組み合わさる時だけ候補化する]
    #   処理: [1: black screen OCR boxを分析する 2: title Keep/Drop/Separate policyを検証する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_text_only_and_title_policies(self) -> None:
        black = self._frame(np.zeros((64, 64, 3), dtype=np.uint8))
        one_line = (FrameTextBox(0.42, 0.45, 0.16, 0.06, text="TITLE"),)
        base = FrameFilterOptions(enabled=True, preset=FrameFilterPreset.BALANCED)
        kept = analyze_frame_sequence("title", (black,), base, text_boxes={0: one_line}).reports[0]
        dropped = analyze_frame_sequence(
            "title",
            (black,),
            FrameFilterOptions(
                enabled=True,
                preset=FrameFilterPreset.BALANCED,
                title_credits_policy="drop",
            ),
            text_boxes={0: one_line},
        ).reports[0]
        separated = analyze_frame_sequence(
            "title",
            (black,),
            FrameFilterOptions(
                enabled=True,
                preset=FrameFilterPreset.BALANCED,
                title_credits_policy="separate",
            ),
            text_boxes={0: one_line},
        ).reports[0]

        self.assertIn("text_only_low_visual_information", kept.reasons)
        self.assertIn("title_card", kept.reasons)
        self.assertEqual(kept.decision, FrameFilterDecision.KEEP)
        self.assertEqual(dropped.decision, FrameFilterDecision.DROP)
        self.assertEqual(separated.decision, FrameFilterDecision.REVIEW)

    # {
    #   責務: [test_neighbor_context_and_decode_failure_are_separate: fade contextとdecoder errorを区別する]
    #   処理: [1: textured-neighbor付きblack frameを分析する 2: decode failureをERRORにする]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_neighbor_context_and_decode_failure_are_separate(self) -> None:
        rng = np.random.default_rng(284)
        scene = self._frame(rng.integers(20, 230, size=(48, 48, 3), dtype=np.uint8))
        blank = self._frame(np.zeros((48, 48, 3), dtype=np.uint8))
        failed = normalize_decoded_frame(
            DecodedVideoFrame(
                None,
                "rgb24",
                actual_timestamp=1.0,
                decode_status=FrameDecodeStatus.DECODE_FAILED,
            )
        )
        options = FrameFilterOptions(
            enabled=True,
            preset=FrameFilterPreset.BALANCED,
            compare_neighbors=True,
            action=FrameFilterAction.REVIEW_QUEUE,
            detect_text_only=False,
            detect_title_credits=False,
        )

        result = analyze_frame_sequence("transition", (scene, blank, scene, failed), options)

        self.assertIn("fade_or_transition", result.reports[1].reasons)
        self.assertEqual(result.reports[3].decision, FrameFilterDecision.ERROR)
        self.assertEqual(result.reports[3].reasons, ("decode:decode_failed",))
        self.assertEqual((result.review_count, result.error_count), (0, 1))

    # {
    #   責務: [test_disabled_mode_keeps_frames_and_options_are_validated: default offとOCR geometry validationを確認する]
    #   処理: [1: filter-disabled resultを検証する 2: out-of-bounds OCR boxを拒否する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_disabled_mode_keeps_frames_and_options_are_validated(self) -> None:
        black = self._frame(np.zeros((16, 16, 3), dtype=np.uint8))
        result = analyze_frame_sequence("disabled", (black,))
        self.assertEqual(result.reports[0].decision, FrameFilterDecision.KEEP)
        self.assertEqual(result.reports[0].reasons, ("filter_disabled",))
        with self.assertRaisesRegex(ValueError, "normalized frame bounds"):
            analyze_frame_sequence(
                "invalid",
                (black,),
                FrameFilterOptions(enabled=True),
                text_boxes={0: (FrameTextBox(0.9, 0.9, 0.2, 0.2),)},
            )

    # {
    #   責務: [test_custom_threshold_overrides_are_applied: custom presetのthresholdを実判定へ反映する]
    #   処理: [1: nearly black imageを作る 2: extreme ratio overrideで候補から外す 3: out-of-range overrideを拒否する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_custom_threshold_overrides_are_applied(self) -> None:
        pixels = np.zeros((32, 32, 3), dtype=np.uint8)
        pixels[0, 0] = 255
        frame = self._frame(pixels)
        options = FrameFilterOptions(
            enabled=True,
            preset=FrameFilterPreset.CUSTOM,
            detect_low_detail=False,
            detect_text_only=False,
            detect_title_credits=False,
            custom_extreme_ratio_threshold=0.9999,
        )

        report = analyze_frame_sequence("custom", (frame,), options).reports[0]

        self.assertEqual(report.decision, FrameFilterDecision.KEEP)
        self.assertEqual(report.black_ratio, 1023 / 1024)
        with self.assertRaisesRegex(ValueError, "thresholds or provenance"):
            analyze_frame_sequence(
                "invalid-custom",
                (frame,),
                FrameFilterOptions(enabled=True, custom_candidate_threshold=1.5),
            )


if __name__ == "__main__":
    unittest.main()
