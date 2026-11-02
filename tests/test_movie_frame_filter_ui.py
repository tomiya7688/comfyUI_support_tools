"""Tests for Movie Frames filter UI wiring."""

from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.tabs.screenshot_from_movie import ScreenshotFromMovieTab


# {
#   責務: [MovieFrameFilterUiTests: existing-frame actionが専用sourceを使うことを検証する]
#   フィールド: [filter service callのsource/output/options/dry-run引数]
# }
class MovieFrameFilterUiTests(unittest.TestCase):
    # {
    #   責務: [test_existing_frame_filter_uses_selected_source: video inputを既存画像folderとして誤用しない]
    #   処理: [1: tab dependencyをfakeする 2: click handlerを実行する 3: filter service引数を照合する]
    #   引数: []
    #   戻り値: []
    # }
    def test_existing_frame_filter_uses_selected_source(self):
        calls = []

        # {
        #   責務: [fake_filter: UI接続の引数を記録しテスト用summaryを返す]
        #   処理: [1: filter service引数を保存する 2: count summaryを返す]
        #   引数: [source/destination/options/dry_run]
        #   戻り値: [fake manifest summary]
        # }
        def fake_filter(source, destination, options, *, dry_run):
            calls.append((source, destination, options, dry_run))
            return SimpleNamespace(kept_count=1, dropped_count=2, review_count=3, error_count=0)

        tab = SimpleNamespace(
            existing_frames_dir=SimpleNamespace(get=lambda: "/tmp/source-frames"),
            output_dir=SimpleNamespace(get=lambda: "/tmp/movie-output"),
            _filter_options=lambda: "options",
            filter_preview_only=SimpleNamespace(get=lambda: True),
            logbox=SimpleNamespace(log=lambda _message: None),
        )
        with patch("scripts.tabs.screenshot_from_movie.filter_existing_frame_folder", fake_filter):
            ScreenshotFromMovieTab.filter_existing_frames(tab)

        self.assertEqual(
            calls,
            [
                (
                    Path("/tmp/source-frames"),
                    Path("/tmp/movie-output/filtered_frames"),
                    "options",
                    True,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
