"""Scoring and aggregation checks for generation resource telemetry."""

import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.shared.fast_generation import (
    GenerationHistory,
    GenerationMeasurement,
    quality_per_gib,
    quality_per_second,
    summarize_generation_history,
)


# {
#   責務: [FastGenerationMetricsTests: observation boundariesとscoring aggregationを検証する]
#   フィールド: [efficiency and aggregate telemetry validation cases]
# }
class FastGenerationMetricsTests(unittest.TestCase):
    # {
    #   責務: [test_efficiency_scores_require_observed_nonzero_metrics: 不明や0除算を効率値にしない]
    #   処理: [unknown VRAM, missing score, and zero latency remain unscored while known metrics are divided]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_efficiency_scores_require_observed_nonzero_metrics(self) -> None:
        known = GenerationMeasurement("draft", "model-a", 2, 4, prompt_alignment=0.8)
        unknown_vram = GenerationMeasurement("draft", "model-b", 2, None, prompt_alignment=0.8)
        no_score = GenerationMeasurement("draft", "model-c", 2, 4)
        zero_latency = GenerationMeasurement("draft", "model-d", 0, 4, prompt_alignment=0.8)

        self.assertEqual(quality_per_second(known), 0.4)
        self.assertEqual(quality_per_gib(known), 0.2)
        self.assertIsNone(quality_per_gib(unknown_vram))
        self.assertIsNone(quality_per_second(no_score))
        self.assertIsNone(quality_per_second(zero_latency))

    # {
    #   責務: [test_summaries_group_profiles_and_keep_unknown_observations: profile別に実測のみ集計する]
    #   処理: [append known and unknown observations, then check averages and missing quality remain explicit]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_summaries_group_profiles_and_keep_unknown_observations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            history = GenerationHistory(Path(temporary_directory) / "history.jsonl")
            history.append(
                GenerationMeasurement(
                    "draft", "model-a", 2, 4, prompt_alignment=0.8, artifact=False
                )
            )
            history.append(GenerationMeasurement("draft", "model-b", 4, None))
            history.append(GenerationMeasurement("quality", "model-c", 10, 8))

            summaries = summarize_generation_history(Path(temporary_directory) / "history.jsonl")

        self.assertEqual([item.profile_id for item in summaries], ["draft", "quality"])
        draft = summaries[0]
        self.assertEqual(draft.sample_count, 2)
        self.assertEqual(draft.average_latency_seconds, 3)
        self.assertEqual(draft.images_per_minute, 20)
        self.assertEqual(draft.average_peak_vram_gib, 4)
        self.assertEqual(draft.artifact_rate, 0)
        self.assertEqual(draft.average_prompt_alignment, 0.8)
        self.assertEqual(draft.average_quality_per_second, 0.4)
        self.assertEqual(draft.average_quality_per_gib, 0.2)


if __name__ == "__main__":
    unittest.main()
