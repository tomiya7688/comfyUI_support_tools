"""Focused coverage for duplicate-safe train/validation assignment."""

from __future__ import annotations

import unittest
from pathlib import Path

from comfyui_support_tools.applications.lora_dataset_curator.process.processing.split import (
    sample_weights,
    split_by_duplicate_group,
)


# {
# 責務: [DatasetCuratorSplitTests: validate deterministic duplicate-safe split behavior]
# フィールド: [none: tests use synthetic paths and group evidence]
# 処理: [protect duplicate groups and verify rare-attribute-aware assignment and bounded weights]
# 引数: [None: unittest fixture]
# 戻り値: [None: tests report split contract]
# }
class DatasetCuratorSplitTests(unittest.TestCase):
    # {
    # 責務: [test_duplicate_members_never_cross_split_boundary: prevent validation leakage]
    # 処理: [assign a duplicate group and assert every member receives one shared split]
    # 引数: [self: test case]
    # 戻り値: [None: all duplicate members remain isolated]
    # }
    def test_duplicate_members_never_cross_split_boundary(self):
        first, duplicate, rare, common = map(
            Path, ("first.png", "copy.png", "rare.png", "common.png")
        )
        groups = {
            first: ("duplicate", "exact", 2),
            duplicate: ("duplicate", "exact", 2),
            rare: ("rare", "none", 1),
            common: ("common", "none", 1),
        }
        attributes = {
            first: (("pose", ("front",)),),
            duplicate: (("pose", ("front",)),),
            rare: (("pose", ("back",)),),
            common: (("pose", ("front",)),),
        }
        split = split_by_duplicate_group(groups, attributes, validation_ratio=0.25, seed=7)
        self.assertEqual(split[first], split[duplicate])
        self.assertEqual(split[rare], "validation")
        self.assertEqual(split[first], "train")

    # {
    # 責務: [test_sample_weights_are_positive_bounded_and_reduce_duplicates: avoid duplicate oversampling]
    # 処理: [apply duplicate and low-priority discounts while clamping a manual override]
    # 引数: [self: test case]
    # 戻り値: [None: every weight stays inside the configured range]
    # }
    def test_sample_weights_are_positive_bounded_and_reduce_duplicates(self):
        duplicate, unique, excluded = map(Path, ("duplicate.png", "unique.png", "excluded.png"))
        groups = {
            duplicate: ("dup", "exact", 2),
            unique: ("unique", "none", 1),
            excluded: ("excluded", "none", 1),
        }
        weights = sample_weights(
            groups,
            {},
            maximum=2.0,
            low_weight={excluded},
            overrides={unique: 4.0},
        )
        self.assertLess(weights[duplicate], weights[unique])
        self.assertEqual(weights[unique], 2.0)
        self.assertEqual(weights[excluded], 0.25)
        self.assertTrue(all(0.05 <= value <= 2.0 for value in weights.values()))


if __name__ == "__main__":
    unittest.main()
