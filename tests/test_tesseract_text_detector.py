"""Tests for the optional local OCR frame-filter adapter."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

import numpy as np

from comfyui_support_tools.shared.contracts.frame_filter import FrameTextBox
from comfyui_support_tools.shared.tesseract_text_detector import (
    TesseractTextDetector,
    _parse_tsv_lines,
)

TSV_HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


# {
#   責務: [TesseractTextDetectorTests: local OCRをline単位のbounded normalized boxesへ変換する]
#   フィールド: [fake Tesseract subprocess outputs]
# }
class TesseractTextDetectorTests(unittest.TestCase):
    # {
    #   責務: [test_tsv_words_are_grouped_by_line_and_normalized: TSV word boxesをline単位に集約する]
    #   処理: [1: word行2行分をparseする 2: bbox/confidence/text groupingを確認する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_tsv_words_are_grouped_by_line_and_normalized(self) -> None:
        content = "\n".join(
            (
                TSV_HEADER,
                "5\t1\t1\t1\t1\t1\t10\t8\t20\t10\t90\tCREDIT",
                "5\t1\t1\t1\t1\t2\t34\t8\t18\t10\t80\tROLL",
                "5\t1\t1\t1\t2\t1\t5\t30\t25\t8\t-1\t",
            )
        )
        boxes = _parse_tsv_lines(content, 100, 50)
        self.assertEqual(
            boxes,
            (FrameTextBox(0.1, 0.16, 0.42, 0.2, 0.85, "CREDIT ROLL"),),
        )

    # {
    #   責務: [test_detector_checks_engine_and_passes_rgb_png_to_tesseract: adapterが実行環境を検査しlocal PNGをTSV OCRへ渡す]
    #   処理: [1: version/lang/image commandをfakeする 2: command argsとOCR boxesを確認する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_detector_checks_engine_and_passes_rgb_png_to_tesseract(self) -> None:
        responses = [
            subprocess.CompletedProcess([], 0, b"tesseract 5.5.0\n", b""),
            subprocess.CompletedProcess(
                [], 0, b"List of available languages (2):\neng\njpn\n", b""
            ),
            subprocess.CompletedProcess(
                [],
                0,
                (TSV_HEADER + "\n5\t1\t1\t1\t1\t1\t10\t8\t20\t10\t95\t字幕\n").encode(),
                b"",
            ),
        ]
        with (
            patch(
                "comfyui_support_tools.shared.tesseract_text_detector.shutil.which",
                return_value="/usr/bin/tesseract",
            ),
            patch(
                "comfyui_support_tools.shared.tesseract_text_detector.subprocess.run",
                side_effect=responses,
            ) as run,
        ):
            detector = TesseractTextDetector()
            boxes = detector(np.zeros((50, 100, 3), dtype=np.uint8))

        self.assertEqual(detector.version, "tesseract 5.5.0")
        self.assertEqual(detector.languages, "jpn+eng")
        self.assertEqual(boxes, (FrameTextBox(0.1, 0.16, 0.2, 0.2, 0.95, "字幕"),))
        command = run.call_args_list[-1]
        self.assertEqual(command.args[0][3:], ["-l", "jpn+eng", "--psm", "11", "tsv"])
        self.assertTrue(command.kwargs["input"].startswith(b"\x89PNG\r\n\x1a\n"))

    # {
    #   責務: [test_missing_executable_and_malformed_tsv_fail_closed: OCR未導入/破損応答を成功扱いしない]
    #   処理: [1: executable欠落を拒否する 2: malformed TSVを検出する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_missing_executable_and_malformed_tsv_fail_closed(self) -> None:
        with patch(
            "comfyui_support_tools.shared.tesseract_text_detector.shutil.which", return_value=None
        ):
            with self.assertRaisesRegex(FileNotFoundError, "Tesseract is required"):
                TesseractTextDetector()
        with self.assertRaisesRegex(ValueError, "malformed TSV"):
            _parse_tsv_lines(
                TSV_HEADER + "\n5\t1\t1\t1\t1\t1\tbad\t0\t3\t4\t80\tX",
                100,
                50,
            )


if __name__ == "__main__":
    unittest.main()
