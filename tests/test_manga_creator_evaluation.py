"""Focused tests for transparent manga panel quality proxies."""

from __future__ import annotations

import unittest

from comfyui_support_tools.applications.manga_creator.process.processing.evaluation import (
    evaluate_panel_dimensions,
)
from comfyui_support_tools.shared.contracts.manga_creator import (
    DialogueLine,
    MangaLayoutMode,
    MangaPage,
    MangaProject,
    MangaStyleMode,
    PanelSpec,
    ReadingDirection,
)


# {
# 責務: [MangaCreatorEvaluationTests: verify ranking proxies and honesty about unmeasured image qualities]
# フィールド: [none: use minimal in-memory project and panel contracts]
# 処理: [check resolution/aspect behavior and surface semantic limitations]
# 引数: [None: unittest fixture]
# 戻り値: [None: tests report evaluation contract]
# }
class MangaCreatorEvaluationTests(unittest.TestCase):
    # {
    # 責務: [test_resolution_proxy_rewards_sufficient_dimensions: validate the measured resolution signal]
    # 処理: [compare undersized and sufficiently large candidate dimensions]
    # 引数: [self: test case]
    # 戻り値: [None: larger output receives a no-worse resolution score]
    # }
    def test_resolution_proxy_rewards_sufficient_dimensions(self):
        panel = PanelSpec(id="panel-1", page_id="p1", order=0, bbox=(0.1, 0.1, 0.4, 0.6))
        page = MangaPage("p1", 1, MangaLayoutMode.MANGA_PAGE, (panel,))
        project = MangaProject(
            id="test",
            title="Test",
            premise="A test story",
            genre="slice_of_life",
            target_page_count=1,
            reading_direction=ReadingDirection.RIGHT_TO_LEFT,
            style=MangaStyleMode.STORYBOARD,
            layout_mode=MangaLayoutMode.MANGA_PAGE,
            story_script="A simple scene.",
            pages=(page,),
        )
        low = evaluate_panel_dimensions(project, page, panel, (320, 480))
        high = evaluate_panel_dimensions(project, page, panel, (640, 960))
        low_scores = dict(low.scores)
        high_scores = dict(high.scores)
        self.assertLess(
            low_scores["minimum_resolution_proxy"], high_scores["minimum_resolution_proxy"]
        )
        self.assertIn("OCR", " ".join(high.limitations))

    # {
    # 責務: [test_dialogue_density_proxy_is_bounded: prevent overflow from producing invalid rankings]
    # 処理: [score a long dialogue candidate using the documented bounded proxy]
    # 引数: [self: test case]
    # 戻り値: [None: all returned quality proxies remain normalized]
    # }
    def test_dialogue_density_proxy_is_bounded(self):
        project = MangaProject(
            id="test",
            title="Test",
            premise="A test story",
            genre="slice_of_life",
            target_page_count=1,
            reading_direction=ReadingDirection.RIGHT_TO_LEFT,
            style=MangaStyleMode.STORYBOARD,
            layout_mode=MangaLayoutMode.MANGA_PAGE,
            story_script="A simple scene.",
            pages=(
                MangaPage(
                    "p1",
                    1,
                    MangaLayoutMode.MANGA_PAGE,
                    (PanelSpec("panel-1", "p1", 0, (0.1, 0.1, 0.4, 0.6)),),
                ),
            ),
        )
        panel = PanelSpec(
            id="panel-1",
            page_id="p1",
            order=0,
            bbox=(0.1, 0.1, 0.4, 0.6),
            dialogue=(DialogueLine(id="line-1", text="dialogue " * 80),),
        )
        evaluation = evaluate_panel_dimensions(project, project.pages[0], panel, (640, 960))
        scores = dict(evaluation.scores)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in scores.values()))
        self.assertEqual(scores["dialogue_density_proxy"], 0.0)


if __name__ == "__main__":
    unittest.main()
