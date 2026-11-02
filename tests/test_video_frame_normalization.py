"""Backend-neutral video frame normalization regression tests."""

import unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from comfyui_support_tools.shared.contracts.frame_analysis import (
    ActivePictureRect,
    DecodedVideoFrame,
    FrameDecodeStatus,
)
from comfyui_support_tools.shared.video_frame_normalization import (
    decode_frame_for_analysis,
    detect_active_picture,
    normalize_decoded_frame,
    normalize_frame_sequence,
)


# {
#   責務: [VideoFrameNormalizationTests: normalized video frame contractを検証する]
#   フィールド: [temporal black bar、HDR/range、VFR timing、decode status]
# }
class VideoFrameNormalizationTests(unittest.TestCase):
    # {
    #   責務: [test_bars_are_removed_only_after_temporal_confirmation: temporal consistencyと暗い映像保護を検証する]
    #   処理: [1: black-bar frameを複数時点で正規化する 2: 安定rectを確認する 3: 単一/暗転frameはcropしない]
    #   引数: []
    #   戻り値: []
    # }
    def test_bars_are_removed_only_after_temporal_confirmation(self):
        frame_pixels = np.full((24, 32, 3), 140, dtype=np.uint8)
        frame_pixels[:4] = 0
        frame_pixels[-4:] = 0
        raw_frames = (
            DecodedVideoFrame(
                frame_pixels,
                "rgb24",
                requested_timestamp=1.0,
                actual_timestamp=1.04,
                pts=26,
                time_base=Fraction(1, 25),
            ),
            DecodedVideoFrame(
                frame_pixels.copy(),
                "rgb24",
                requested_timestamp=2.0,
                actual_timestamp=2.04,
                pts=51,
                time_base=Fraction(1, 25),
            ),
        )
        first, second = normalize_frame_sequence(raw_frames)
        self.assertIsNone(detect_active_picture((first,)))
        self.assertEqual(
            detect_active_picture((first, second)),
            ActivePictureRect(0, 4, 32, 16),
        )
        self.assertEqual(first.active_picture_rect, ActivePictureRect(0, 4, 32, 16))
        self.assertEqual(second.active_picture_rect, ActivePictureRect(0, 4, 32, 16))
        dark = normalize_decoded_frame(
            DecodedVideoFrame(
                np.zeros((24, 32, 3), dtype=np.uint8),
                "rgb24",
                actual_timestamp=3.0,
            )
        )
        self.assertIsNone(detect_active_picture((first, dark)))

    # {
    #   責務: [test_hdr_limited_range_and_sdr_map_to_comparable_luminance: HDR/limited rangeを解析用canonical luminanceへ写像する]
    #   処理: [1: SDR full-rangeを変換する 2: 10-bit BT.2020 PQ limitedを変換する 3: luminance差をboundedに確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_hdr_limited_range_and_sdr_map_to_comparable_luminance(self):
        sdr = normalize_decoded_frame(
            DecodedVideoFrame(
                np.full((4, 4, 3), 128, dtype=np.uint8),
                "rgb24",
                transfer_function="srgb",
                actual_timestamp=1.0,
            )
        )
        supported_hdr = normalize_decoded_frame(
            DecodedVideoFrame(
                np.full((4, 4, 3), 502, dtype=np.uint16),
                "rgb48",
                color_primaries="bt2020",
                transfer_function="pq",
                color_range="limited",
                matrix_coefficients="bt2020-ncl",
                actual_timestamp=1.0,
                pts=90000,
                time_base=Fraction(1, 90000),
                stream_metadata={"bits_per_component": 10, "max_luminance_nits": 1000},
            )
        )
        self.assertTrue(sdr.has_pixels)
        self.assertTrue(supported_hdr.has_pixels)
        self.assertEqual(supported_hdr.canonical_colorspace, "linear-srgb-d65")
        self.assertLess(
            abs(float(np.mean(sdr.luminance)) - float(np.mean(supported_hdr.luminance))),
            0.12,
        )

    # {
    #   責務: [test_timestamps_and_explicit_decode_errors_survive_normalization: VFR timelineとdecode error contractを検証する]
    #   処理: [1: PTS/time_baseからactual timeを復元する 2: decode errorをpixels無しで保持する 3: timestamp欠落を明示する]
    #   引数: []
    #   戻り値: []
    # }
    def test_timestamps_and_explicit_decode_errors_survive_normalization(self):
        decoded = normalize_decoded_frame(
            DecodedVideoFrame(
                np.full((2, 3, 3), 255, dtype=np.uint8),
                "rgb24",
                requested_timestamp=0.99,
                pts=26,
                time_base=Fraction(1, 25),
            )
        )
        self.assertEqual(decoded.requested_timestamp, 0.99)
        self.assertEqual(decoded.actual_timestamp, 1.04)
        self.assertEqual(decoded.pts, 26)
        self.assertEqual(decoded.time_base, Fraction(1, 25))
        backend_inputs = []
        for backend_name in ("libav", "ffmpeg_cli"):
            decoded_source = DecodedVideoFrame(
                np.full((2, 3, 3), 255, dtype=np.uint8),
                "rgb24",
                actual_timestamp=1.04,
                pts=26,
                time_base=Fraction(1, 25),
                stream_metadata={"adapter": backend_name},
            )
            adapter = SimpleNamespace(
                decode_frame=lambda _source, _timestamp, result=decoded_source: result
            )
            backend_inputs.append(decode_frame_for_analysis(adapter, Path("video.mp4"), 0.99))
        self.assertEqual(
            backend_inputs[0].canonical_colorspace, backend_inputs[1].canonical_colorspace
        )
        np.testing.assert_array_equal(backend_inputs[0].luminance, backend_inputs[1].luminance)
        self.assertEqual(backend_inputs[0].requested_timestamp, 0.99)
        self.assertEqual(backend_inputs[0].actual_timestamp, 1.04)
        failed = normalize_decoded_frame(
            DecodedVideoFrame(
                None,
                "rgb24",
                width=1920,
                height=1080,
                requested_timestamp=4.0,
                decode_status="decode_failed",
                error="demuxer error",
            )
        )
        self.assertEqual(failed.decode_status, FrameDecodeStatus.DECODE_FAILED)
        self.assertFalse(failed.has_pixels)
        self.assertEqual(failed.width, 1920)
        self.assertEqual(failed.error, "demuxer error")
        unresolved = normalize_decoded_frame(
            DecodedVideoFrame(np.ones((2, 3, 3), dtype=np.uint8), "rgb24")
        )
        self.assertEqual(unresolved.decode_status, FrameDecodeStatus.TIMESTAMP_UNRESOLVED)
        self.assertFalse(unresolved.has_pixels)

    # {
    #   責務: [test_user_override_and_invalid_inputs_are_explicit: active rect overrideとpixel validationを検証する]
    #   処理: [1: valid overrideを尊重する 2: out-of-bounds overrideを拒否する 3: unsupported format/errorを分離する]
    #   引数: []
    #   戻り値: []
    # }
    def test_user_override_and_invalid_inputs_are_explicit(self):
        frame = normalize_decoded_frame(
            DecodedVideoFrame(
                np.full((20, 40, 3), 200, dtype=np.uint8),
                "rgb24",
                actual_timestamp=1.0,
            )
        )
        override = ActivePictureRect(2, 3, 35, 16)
        self.assertEqual(detect_active_picture((frame,), user_override=override), override)
        with self.assertRaises(ValueError):
            detect_active_picture((frame,), user_override=ActivePictureRect(39, 0, 2, 20))
        unsupported = normalize_decoded_frame(
            DecodedVideoFrame(
                np.zeros((20, 40, 3), dtype=np.uint8),
                "yuv420p",
                actual_timestamp=1.0,
            )
        )
        self.assertEqual(unsupported.decode_status, FrameDecodeStatus.UNSUPPORTED_PIXEL_FORMAT)
        unsupported_transfer = normalize_decoded_frame(
            DecodedVideoFrame(
                np.zeros((20, 40, 3), dtype=np.uint8),
                "rgb24",
                transfer_function="vendor-unknown",
                actual_timestamp=1.0,
            )
        )
        self.assertEqual(
            unsupported_transfer.decode_status,
            FrameDecodeStatus.UNSUPPORTED_COLOR_METADATA,
        )
        corrupted = normalize_decoded_frame(
            DecodedVideoFrame(
                np.full((20, 40, 3), np.nan, dtype=np.float32),
                "rgb24",
                actual_timestamp=1.0,
            )
        )
        self.assertEqual(corrupted.decode_status, FrameDecodeStatus.CORRUPTED)

    # {
    #   責務: [test_malformed_color_metadata_is_explicit_and_hlg_aliases_agree: malformed stream tagsとHLG aliasを検証する]
    #   処理: [1: HLG aliasesを正規化する 2: invalid tagをINVALID_FRAMEへ変換する]
    #   引数: []
    #   戻り値: []
    # }
    def test_malformed_color_metadata_is_explicit_and_hlg_aliases_agree(self):
        pixels = np.full((2, 2, 3), 0.5, dtype=np.float32)
        options = {
            "actual_timestamp": 1.0,
            "stream_metadata": {"max_luminance_nits": 1000.0},
        }
        hlg = normalize_decoded_frame(
            DecodedVideoFrame(pixels, "rgb24", transfer_function="hlg", **options)
        )
        alias = normalize_decoded_frame(
            DecodedVideoFrame(pixels, "rgb24", transfer_function="ARIB-STD-B67", **options)
        )
        np.testing.assert_allclose(hlg.analysis_rgb, alias.analysis_rgb)
        malformed = normalize_decoded_frame(
            DecodedVideoFrame(pixels, "rgb24", color_primaries=None, actual_timestamp=1.0)
        )
        self.assertEqual(malformed.decode_status, FrameDecodeStatus.INVALID_FRAME)
        self.assertFalse(malformed.has_pixels)


if __name__ == "__main__":
    unittest.main()
