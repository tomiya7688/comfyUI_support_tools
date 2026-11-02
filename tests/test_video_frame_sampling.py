"""Deterministic movie frame count, refill, and lineage regression tests."""

import unittest
from fractions import Fraction

import numpy as np

from comfyui_support_tools.shared.contracts.frame_analysis import (
    DecodedVideoFrame,
    FrameDecodeStatus,
)
from comfyui_support_tools.shared.contracts.frame_sampling import (
    FrameCountMode,
    FrameEvaluation,
    FrameSamplingOptions,
    SamplingBin,
)
from comfyui_support_tools.shared.video_frame_normalization import normalize_decoded_frame
from comfyui_support_tools.shared.video_frame_sampling import sample_video_frames


# {
#   責務: [VideoFrameSamplingTests: deterministic bounded frame sampling contractを検証する]
#   フィールド: [count mode、replacement、distribution、seed再現性、budget、lineage]
# }
class VideoFrameSamplingTests(unittest.TestCase):
    # {
    #   責務: [test_small_initial_counts_are_distributed_across_seeded_bins: 少数候補を常に冒頭binへ偏らせない]
    #   処理: [1: seed違いのone-frame planを作る 2: 複数時間binが選ばれることを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_small_initial_counts_are_distributed_across_seeded_bins(self):
        # {
        #   責務: [evaluator: 正常解析済みframeを常にkeepするtest adapter]
        #   処理: [1: requested timeでframe metadataを作る 2: keep判定を返す]
        #   引数: [timestamp: candidate requested time]
        #   戻り値: [FrameEvaluation: valid accepted frame]
        # }
        def evaluator(timestamp):
            frame = normalize_decoded_frame(
                DecodedVideoFrame(
                    np.full((2, 2, 3), 128, dtype=np.uint8),
                    "rgb24",
                    actual_timestamp=timestamp,
                )
            )
            return FrameEvaluation(frame, True)

        selected_bins = {
            sample_video_frames(
                "video-small",
                100,
                1,
                evaluator,
                FrameSamplingOptions(sampling_seed=seed, bin_count=10),
            )
            .kept[0]
            .bin_id
            for seed in range(20)
        }
        self.assertGreater(len(selected_bins), 1)

    # {
    #   責務: [test_target_kept_refills_same_time_bins_and_is_seed_deterministic: target count補充と時間分布を検証する]
    #   処理: [1: 30%候補をdropする 2: 同じbin内で補充する 3: seed再現と100件の分布を照合する]
    #   引数: []
    #   戻り値: []
    # }
    def test_target_kept_refills_same_time_bins_and_is_seed_deterministic(self):
        # {
        #   責務: [evaluator: time-bin内30%をdropし残りをkeepするtest filter]
        #   処理: [1: requested timeからbinを決める 2: normalized frameとfilter decisionを返す]
        #   引数: [timestamp: candidate requested time]
        #   戻り値: [FrameEvaluation: low-information判定]
        # }
        def evaluator(timestamp):
            bin_id = int(timestamp // 100)
            within_bin = timestamp - bin_id * 100
            frame = normalize_decoded_frame(
                DecodedVideoFrame(
                    np.full((2, 2, 3), 128, dtype=np.uint8),
                    "rgb24",
                    requested_timestamp=timestamp,
                    actual_timestamp=timestamp + 0.04,
                    pts=round((timestamp + 0.04) * 25),
                    time_base=Fraction(1, 25),
                )
            )
            return FrameEvaluation(frame, within_bin >= 30, "low_information")

        options = FrameSamplingOptions(
            count_mode=FrameCountMode.TARGET_KEPT,
            sampling_seed=404,
            bin_count=10,
            max_attempts=1000,
            max_candidate_multiplier=3,
            max_wall_time_seconds=10,
        )
        result = sample_video_frames("video-1", 1000, 100, evaluator, options)
        repeat = sample_video_frames("video-1", 1000, 100, evaluator, options)
        self.assertEqual(result, repeat)
        self.assertEqual(result.exhausted_reason, "target_reached")
        self.assertEqual(len(result.kept), 100)
        self.assertEqual(result.options, options)
        self.assertEqual(len(result.bins), 10)
        self.assertGreaterEqual(len(result.attempts), 130)
        self.assertEqual(sum(item.sample_generation == "initial" for item in result.attempts), 100)
        self.assertEqual(
            sum(item.sample_generation == "replacement" for item in result.attempts),
            len(result.attempts) - 100,
        )
        self.assertTrue(all(item.filter_result == "keep" for item in result.kept))
        kept_per_bin = {}
        for item in result.kept:
            kept_per_bin[item.bin_id] = kept_per_bin.get(item.bin_id, 0) + 1
            self.assertIsNotNone(item.actual_timestamp)
            self.assertIsNotNone(item.pts)
            self.assertEqual(item.time_base, Fraction(1, 25))
        self.assertEqual(set(kept_per_bin.values()), {10})
        records = {item.candidate_id: item for item in result.attempts}
        for replacement in (
            item for item in result.attempts if item.sample_generation == "replacement"
        ):
            parent = records[replacement.parent_candidate_id]
            self.assertEqual(parent.filter_result, "low_information")
            self.assertEqual(parent.bin_id, replacement.bin_id)

    # {
    #   責務: [test_candidate_count_keeps_filter_drops_without_refill: candidate-count semanticsを検証する]
    #   処理: [1: 固定候補数を評価する 2: reject分を保持する 3: replacementが無いことを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_candidate_count_keeps_filter_drops_without_refill(self):
        # {
        #   責務: [evaluator: 各time binの先頭30%をdropするtest filter]
        #   処理: [1: normalized frameを作る 2: low-information判定を返す]
        #   引数: [timestamp: candidate requested time]
        #   戻り値: [FrameEvaluation: filter result]
        # }
        def evaluator(timestamp):
            frame = normalize_decoded_frame(
                DecodedVideoFrame(
                    np.full((2, 2, 3), 128, dtype=np.uint8),
                    "rgb24",
                    actual_timestamp=timestamp,
                )
            )
            within_bin = timestamp % 10
            return FrameEvaluation(frame, within_bin >= 3, "dark")

        result = sample_video_frames(
            "video-2",
            100,
            100,
            evaluator,
            FrameSamplingOptions(
                count_mode=FrameCountMode.CANDIDATE_COUNT,
                sampling_seed=438,
            ),
        )
        self.assertEqual(len(result.attempts), 100)
        self.assertEqual(len(result.kept), 70)
        self.assertEqual(result.exhausted_reason, "candidate_count_complete")
        self.assertTrue(all(item.sample_generation == "initial" for item in result.attempts))

    # {
    #   責務: [test_scene_bins_and_decode_errors_keep_explicit_lineage: scene binsとinvalid frameを処理する]
    #   処理: [1: callerのscene binを使う 2: decode failureをrejectする 3: replacementを同じsceneに限定する]
    #   引数: []
    #   戻り値: []
    # }
    def test_scene_bins_and_decode_errors_keep_explicit_lineage(self):
        bins = (SamplingBin("shot-a", 0, 50), SamplingBin("shot-b", 50, 100))
        calls_in_first_shot = [0]

        # {
        #   責務: [evaluator: first sceneの初期3frameをdecode failureにするtest adapter]
        #   処理: [1: shot-a初期候補を3件失敗させる 2: 残りframeをkeepする]
        #   引数: [timestamp: candidate requested time]
        #   戻り値: [FrameEvaluation: frame/errorとkeep判断]
        # }
        def evaluator(timestamp):
            if timestamp < 50:
                calls_in_first_shot[0] += 1
                if calls_in_first_shot[0] <= 3:
                    frame = normalize_decoded_frame(
                        DecodedVideoFrame(
                            None,
                            "rgb24",
                            width=2,
                            height=2,
                            requested_timestamp=timestamp,
                            decode_status=FrameDecodeStatus.DECODE_FAILED,
                        )
                    )
                    return FrameEvaluation(frame, True)
            frame = normalize_decoded_frame(
                DecodedVideoFrame(
                    np.full((2, 2, 3), 128, dtype=np.uint8),
                    "rgb24",
                    actual_timestamp=timestamp,
                )
            )
            return FrameEvaluation(frame, True)

        result = sample_video_frames(
            "video-3",
            100,
            10,
            evaluator,
            FrameSamplingOptions(sampling_seed=3, max_candidate_multiplier=4),
            bins=bins,
        )
        self.assertEqual(result.exhausted_reason, "target_reached")
        self.assertEqual(len(result.kept), 10)
        failed = [
            item
            for item in result.attempts
            if item.bin_id == "shot-a" and item.filter_result.startswith("decode:")
        ]
        self.assertTrue(failed)
        self.assertTrue(all(item.filter_result == "decode:decode_failed" for item in failed))
        replacements = [item for item in result.kept if item.sample_generation == "replacement"]
        self.assertTrue(all(item.parent_candidate_id for item in replacements))
        self.assertTrue(all(item.bin_id == "shot-a" for item in replacements))

    # {
    #   責務: [test_duplicate_seek_results_do_not_fill_target_count: VFR seekが同じactual frameへ解決する重複を検出する]
    #   処理: [1: 異なるrequested timeから同じPTSを返す 2: 重複をdropしてbudget reasonを返す]
    #   引数: []
    #   戻り値: []
    # }
    def test_duplicate_seek_results_do_not_fill_target_count(self):
        # {
        #   責務: [evaluator: 全requested timeを同じactual PTSへ解決するtest decoder]
        #   処理: [1: 同一decoded frame metadataを返す]
        #   引数: [timestamp: ignored requested time]
        #   戻り値: [FrameEvaluation: same actual frame]
        # }
        def evaluator(_timestamp):
            frame = normalize_decoded_frame(
                DecodedVideoFrame(
                    np.full((2, 2, 3), 128, dtype=np.uint8),
                    "rgb24",
                    actual_timestamp=1.0,
                    pts=25,
                    time_base=Fraction(1, 25),
                )
            )
            return FrameEvaluation(frame, True)

        result = sample_video_frames(
            "video-duplicate",
            100,
            4,
            evaluator,
            FrameSamplingOptions(sampling_seed=438, max_candidate_multiplier=2),
        )
        self.assertEqual(len(result.kept), 1)
        self.assertEqual(result.exhausted_reason, "max_candidate_multiplier")
        self.assertTrue(
            any(item.filter_result == "duplicate_actual_frame" for item in result.attempts)
        )

    # {
    #   責務: [test_attempt_multiplier_and_wall_time_budgets_stop_sampling: exhausted reasonsとbounded loopsを検証する]
    #   処理: [1: all rejectでmultiplier/attempt capへ達する 2: fake clockでwall-time capへ達する]
    #   引数: []
    #   戻り値: []
    # }
    def test_attempt_multiplier_and_wall_time_budgets_stop_sampling(self):
        # {
        #   責務: [rejected: decodeできないframeを返すtest adapter]
        #   処理: [1: decode failure resultを返す]
        #   引数: [timestamp: ignored requested time]
        #   戻り値: [FrameEvaluation: rejected candidate]
        # }
        def rejected(_timestamp):
            return FrameEvaluation(None, False, "decode_failed")

        multiplier_limited = sample_video_frames(
            "video-4",
            100,
            10,
            rejected,
            FrameSamplingOptions(
                sampling_seed=1,
                max_attempts=100,
                max_candidate_multiplier=2,
            ),
        )
        self.assertEqual(len(multiplier_limited.attempts), 20)
        self.assertEqual(multiplier_limited.exhausted_reason, "max_candidate_multiplier")
        attempts_limited = sample_video_frames(
            "video-4",
            100,
            10,
            rejected,
            FrameSamplingOptions(
                sampling_seed=1,
                max_attempts=12,
                max_candidate_multiplier=10,
            ),
        )
        self.assertEqual(len(attempts_limited.attempts), 12)
        self.assertEqual(attempts_limited.exhausted_reason, "max_attempts")

        clock_value = [0.0]

        # {
        #   責務: [slow_reject: fake wall clockを1秒進めるbounded evaluator]
        #   処理: [1: fake timeを進める 2: decode failure resultを返す]
        #   引数: [timestamp: ignored requested time]
        #   戻り値: [FrameEvaluation: rejected candidate]
        # }
        def slow_reject(_timestamp):
            clock_value[0] += 1.0
            return FrameEvaluation(None, False, "decode_failed")

        timed_out = sample_video_frames(
            "video-4",
            100,
            10,
            slow_reject,
            FrameSamplingOptions(sampling_seed=1, max_wall_time_seconds=1.0),
            clock=lambda: clock_value[0],
        )
        self.assertEqual(len(timed_out.attempts), 1)
        self.assertEqual(timed_out.exhausted_reason, "max_wall_time")

    # {
    #   責務: [test_invalid_sampling_budget_or_bins_are_rejected: invalid sampling policyを事前拒否する]
    #   処理: [1: zero budgetを拒否する 2: durationを覆わないscene bin partitionを拒否する]
    #   引数: []
    #   戻り値: []
    # }
    def test_invalid_sampling_budget_or_bins_are_rejected(self):
        with self.assertRaises(ValueError):
            sample_video_frames(
                "video-5",
                10,
                2,
                lambda _timestamp: FrameEvaluation(None, False),
                FrameSamplingOptions(max_attempts=0),
            )
        with self.assertRaises(ValueError):
            sample_video_frames(
                "video-5",
                10,
                2,
                lambda _timestamp: FrameEvaluation(None, False),
                bins=(SamplingBin("incomplete", 0, 9),),
            )


if __name__ == "__main__":
    unittest.main()
