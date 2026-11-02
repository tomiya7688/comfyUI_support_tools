"""Focused validation tests for Pixiv asset and duplicate helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from comfyui_support_tools.shared.pixiv_dataset.helpers import _DuplicateIndex


# {
# 責務: [PixivDatasetHelperTests: validate perceptual indexing without a Pixiv API]
# フィールド: [temporary image fixtures]
# 処理: [check similar artwork is grouped while exact hashes remain distinct]
# }
class PixivDatasetHelperTests(unittest.TestCase):
    # {
    # 責務: [test_perceptual_index_finds_near_duplicate_without_exact_hash]
    # 処理: [index a similar image then query the Hamming-distance candidate path]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_perceptual_index_finds_near_duplicate_without_exact_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.png"
            second = root / "second.png"
            Image.new("RGB", (8, 8), (255, 0, 0)).save(first)
            Image.new("RGB", (8, 8), (250, 0, 0)).save(second)
            index = _DuplicateIndex(root)
            index.add(root, "101", ("sha-first",), ("first.png",))

            self.assertEqual(index.find_exact(("sha-second",), "102"), "")
            self.assertEqual(index.find_near(root, ("second.png",), "102"), "101")
