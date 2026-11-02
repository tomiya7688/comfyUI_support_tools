"""Non-destructive integration tests for existing image-folder filtering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

from comfyui_support_tools.shared.contracts.frame_filter import (
    FrameFilterAction,
    FrameFilterOptions,
    FrameFilterPreset,
    FrameTextBox,
)
from comfyui_support_tools.shared.frame_filter_application import (
    _validate_image,
    filter_existing_frame_folder,
)


# {
#   責務: [FrameFilterApplicationTests: existing image filterがsource保持/dry run/outputを保証する]
#   フィールド: [temporary input/output folders]
# }
class FrameFilterApplicationTests(unittest.TestCase):
    # {
    #   責務: [test_dry_run_and_apply_preserve_source_images: previewは書かずapplyはcopyだけを作る]
    #   処理: [1: recursive input fixtureを作る 2: dry-run countを確認する 3: apply output/manifest/source integrityを確認する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_dry_run_and_apply_preserve_source_images(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "frames"
            nested = source / "video-a"
            nested.mkdir(parents=True)
            black = nested / "frame-000.png"
            detail = nested / "frame-001.png"
            Image.fromarray(np.zeros((32, 32, 3), dtype=np.uint8)).save(black)
            Image.fromarray(
                np.random.default_rng(12).integers(20, 240, (32, 32, 3), dtype=np.uint8)
            ).save(detail)
            original = {path: path.read_bytes() for path in (black, detail)}
            output = root / "filtered"
            options = FrameFilterOptions(
                enabled=True,
                preset=FrameFilterPreset.BALANCED,
                action=FrameFilterAction.DROP,
                detect_text_only=False,
                detect_title_credits=False,
            )

            preview = filter_existing_frame_folder(source, output, options, dry_run=True)
            self.assertEqual(preview.dropped_count, 1)
            self.assertFalse(output.exists())
            applied = filter_existing_frame_folder(source, output, options, dry_run=False)

            self.assertEqual(applied.dropped_count, 1)
            self.assertEqual(applied.kept_count, 1)
            self.assertTrue((output / "kept" / "video-a" / "frame-001.png").is_file())
            self.assertFalse((output / "kept" / "video-a" / "frame-000.png").exists())
            self.assertTrue((output / "frame_filter_manifest.json").is_file())
            self.assertEqual({path: path.read_bytes() for path in original}, original)
            with self.assertRaises(FileExistsError):
                filter_existing_frame_folder(source, output, options, dry_run=False)

    # {
    #   責務: [test_title_separate_and_mark_only_are_non_destructive: title separateとmark-onlyをsource保持で出力する]
    #   処理: [1: text-only imageを作る 2: OCR callbackでtitleを判定する 3: separate/mark-onlyの出力を確認する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_title_separate_and_mark_only_are_non_destructive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "frames"
            source.mkdir()
            title = source / "title.png"
            Image.fromarray(np.zeros((48, 48, 3), dtype=np.uint8)).save(title)
            original = title.read_bytes()
            options = FrameFilterOptions(
                enabled=True,
                preset=FrameFilterPreset.BALANCED,
                action=FrameFilterAction.REVIEW_QUEUE,
                title_credits_policy="separate",
            )

            detector = Mock(return_value=(FrameTextBox(0.3, 0.45, 0.4, 0.1, text="TITLE"),))
            separate_output = root / "separated"

            manifest = filter_existing_frame_folder(
                source,
                separate_output,
                options,
                dry_run=False,
                text_detector=detector,
            )

            self.assertEqual(manifest.review_count, 1)
            self.assertTrue((separate_output / "separate" / "title_cards" / "title.png").is_file())
            mark_only = FrameFilterOptions(
                enabled=True,
                preset=FrameFilterPreset.BALANCED,
                action=FrameFilterAction.MARK_ONLY,
                detect_text_only=False,
                detect_title_credits=False,
            )
            marked_output = root / "marked"
            filter_existing_frame_folder(source, marked_output, mark_only, dry_run=False)
            self.assertEqual(list(marked_output.rglob("*.png")), [])
            self.assertTrue((marked_output / "frame_filter_manifest.json").is_file())
            self.assertEqual(title.read_bytes(), original)

    # {
    #   責務: [test_apply_failure_cleans_staged_output_and_requires_ocr_evidence: OCRとapply publish failureをsilent successにしない]
    #   処理: [1: OCR adapter欠落を拒否する 2: stage copyの2枚目を失敗させる 3: final outputが残らないことを確認する]
    #   引数: [self: test instance]
    #   戻り値: []
    # }
    def test_apply_failure_cleans_staged_output_and_requires_ocr_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            source = root / "frames"
            source.mkdir()
            for name, shade in (("a.png", 0), ("b.png", 64)):
                Image.fromarray(np.full((32, 32, 3), shade, dtype=np.uint8)).save(source / name)
            output = root / "filtered"
            options = FrameFilterOptions(enabled=True)
            with self.assertRaisesRegex(ValueError, "requires a configured OCR detector"):
                filter_existing_frame_folder(source, output, options, dry_run=False)

            options = FrameFilterOptions(
                enabled=True,
                detect_text_only=False,
                detect_title_credits=False,
            )
            calls = 0

            # {
            #   責務: [fail_second_validation: 2件目のstaged imageを失敗させcleanupを検証する]
            #   処理: [1: validation件数を増やす 2: 2件目で再現可能なerrorを起こす]
            #   引数: [path: staged image]
            #   戻り値: []
            # }
            def fail_second_validation(path: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise ValueError("simulated image validation failure")
                _validate_image(path)

            with (
                patch(
                    "comfyui_support_tools.shared.frame_filter_application._validate_image",
                    side_effect=fail_second_validation,
                ),
                self.assertRaisesRegex(ValueError, "simulated image validation failure"),
            ):
                filter_existing_frame_folder(source, output, options, dry_run=False)
            self.assertFalse(output.exists())
            self.assertEqual(len(tuple(source.glob("*.png"))), 2)


if __name__ == "__main__":
    unittest.main()
