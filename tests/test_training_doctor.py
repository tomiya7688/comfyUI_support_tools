"""Tests for fixed validation, balanced scoring, early stopping and checkpoint rollback."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.shared.training_doctor import (
    CheckpointRef,
    EarlyStopPolicy,
    FixedConditions,
    ImageEvidence,
    ImageMetrics,
    ScorePreset,
    TrainingDoctorApplication,
    TrainingTracePoint,
    ValidationTask,
    fixed_validation_plan,
    load_report,
    save_report,
    score_weights_for_task,
)


# {
# 責務: [FakeEvaluator: produce reproducible score evidence and record evaluation inputs]
# フィールド: [quality: test quality mode, calls: exact render requests]
# 処理: [return deterministic metrics derived from checkpoint, prompt and scale]
# 引数: [mode: score curve behavior]
# 戻り値: [None: ready test evaluator]
# }
class FakeEvaluator:
    # {
    # 責務: [__init__: select deterministic evaluation behavior]
    # 処理: [store the score mode and initialize the exact call history]
    # 引数: [self: evaluator instance, mode: named deterministic score curve]
    # 戻り値: [None: fake evaluator ready]
    # }
    def __init__(self, mode: str = "best_early") -> None:
        self.mode = mode
        self.calls = []

    # {
    # 責務: [evaluate: return controlled image-quality evidence]
    # 処理: [record fixed conditions and generate normalized metrics for one sample]
    # 引数: [checkpoint: evaluated model, context: fixed prompt and render conditions]
    # 戻り値: [ImageEvidence: score data plus test preview path]
    # }
    def evaluate(self, checkpoint, context):
        self.calls.append((checkpoint.step, context))
        absent = not context.scenario.trigger_present
        if self.mode == "strength":
            best = context.strength == 0.6
            fidelity = 0.82 if best else 0.72
            control = 0.9 if best else 0.7
            leakage = 0.08 if absent else 0.0
            trigger_score = 0.0
        elif self.mode == "trigger":
            trigger_score = 0.9 if context.scenario.trigger_variant == "token-b" else 0.65
            fidelity = trigger_score if not absent else 0.0
            control = 0.85 if not absent else 0.0
            leakage = 0.08 if absent else 0.0
        elif checkpoint.step <= 10:
            fidelity, control, quality, base, leakage, memory, diversity = (
                0.76,
                0.82,
                0.80,
                0.91,
                0.05,
                0.10,
                0.84,
            )
        else:
            fidelity, control, quality, base, leakage, memory, diversity = (
                0.96,
                0.50,
                0.69,
                0.60,
                0.44,
                0.58,
                0.38,
            )
        if self.mode in {"strength", "trigger"}:
            quality = base = diversity = 0.82
            memory = 0.12
            if self.mode == "trigger" and absent:
                fidelity = control = 0.0
        metrics = ImageMetrics(
            fidelity=fidelity if not absent else 0.0,
            controllability=control if not absent else 0.0,
            quality=quality,
            base_preservation=base if absent else 0.0,
            leakage=leakage,
            memorization=memory,
            diversity=diversity,
        )
        return ImageEvidence(
            metrics, Path(f"preview-{checkpoint.step}-{len(self.calls)}.png"), "a" * 64
        )


# {
# 責務: [TrainingDoctorTests: verify issue acceptance contracts end to end]
# フィールド: [none: each test owns isolated checkpoint artifacts and fake evaluator state]
# 処理: [check matrices, repeatable conditions, score selection, multi-signal stops, metadata and persistence]
# }
class TrainingDoctorTests(unittest.TestCase):
    # {
    # 責務: [setUp: prepare three local checkpoint artifacts]
    # 処理: [create temporary checkpoint files for read-only evaluator validation]
    # 引数: [self: test case]
    # 戻り値: [None: temporary checkpoint fixture ready]
    # }
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.checkpoints = []
        for step in (10, 20, 30):
            path = self.root / f"checkpoint-{step}.safetensors"
            path.write_bytes(b"test checkpoint")
            self.checkpoints.append(CheckpointRef(path, step))

    # {
    # 責務: [tearDown: release temporary checkpoint artifacts]
    # 処理: [remove the isolated temporary directory]
    # 引数: [self: test case]
    # 戻り値: [None: resources released]
    # }
    def tearDown(self) -> None:
        self.directory.cleanup()

    # {
    # 責務: [test_fixed_matrices_cover_each_personalization_task: verify fixed prompt coverage and trigger candidates]
    # 処理: [assert task-specific cases, unique keys, absent trigger, and two named concept variants]
    # 引数: [self: test case]
    # 戻り値: [None: assertion result]
    # }
    def test_fixed_matrices_cover_each_personalization_task(self) -> None:
        character = fixed_validation_plan(
            ValidationTask.CHARACTER, "mira", trigger_candidates=("mira", "mira_v2")
        )
        style = fixed_validation_plan(
            ValidationTask.STYLE, "ink", recommended_tags=("ink wash", "soft shadows")
        )
        object_plan = fixed_validation_plan(ValidationTask.OBJECT, "lamp")
        multi = fixed_validation_plan(ValidationTask.MULTI_CONCEPT, "pair", concepts=("A", "B"))
        self.assertEqual(len(character.scenarios), 13)
        self.assertIn("trigger_with_tags_trigger_1", {case.key for case in style.scenarios})
        self.assertTrue(any(not case.trigger_present for case in object_plan.scenarios))
        multi_prompts = {case.key: case.prompt for case in multi.scenarios}
        self.assertIn("A", multi_prompts["a_only_trigger_1"])
        self.assertIn("B", multi_prompts["b_only_trigger_1"])
        self.assertIn("A together with B", multi_prompts["a_plus_b_trigger_1"])

    # {
    # 責務: [test_best_checkpoint_and_strength_are_selected_with_trigger_metadata: verify balanced report selection]
    # 処理: [score repeated checkpoints, persist/reload report, rollback best, and publish prompt metadata]
    # 引数: [self: test case]
    # 戻り値: [None: assertion result]
    # }
    def test_best_checkpoint_and_strength_are_selected_with_trigger_metadata(self) -> None:
        evaluator = FakeEvaluator("best_early")
        plan = fixed_validation_plan(
            ValidationTask.CHARACTER,
            "mira",
            conditions=FixedConditions(
                seeds=(5, 9),
                resolutions=((768, 768), (1024, 1024)),
                inference_step_sweep=(20, 28),
            ),
        )
        trace = (TrainingTracePoint(10, loss=0.5, vram_gib=15, step_seconds=1.2),)
        report = TrainingDoctorApplication(evaluator).evaluate_checkpoints(
            self.checkpoints[:2], plan, strengths=(0.6, 1.0), trace=trace
        )
        self.assertEqual(report.best_checkpoint, self.checkpoints[0].path)
        self.assertEqual(report.final_checkpoint, self.checkpoints[1].path)
        self.assertEqual(report.overfit_onset, 20)
        self.assertEqual(report.leakage_score, 0.05)
        self.assertTrue(any(sample.preview_path for sample in report.validation_samples))
        self.assertEqual(len(evaluator.calls), 2 * 2 * 7 * 2 * 2 * 2)
        settings = [
            (context.seed, context.sampler, context.inference_steps, context.resolution)
            for _, context in evaluator.calls
        ]
        self.assertEqual(len(set(settings)), 8)
        by_checkpoint = {
            step: {
                (
                    context.scenario.key,
                    context.seed,
                    context.sampler,
                    context.inference_steps,
                    context.resolution,
                    context.strength,
                )
                for evaluated_step, context in evaluator.calls
                if evaluated_step == step
            }
            for step in (10, 20)
        }
        self.assertEqual(by_checkpoint[10], by_checkpoint[20])
        restored = []
        TrainingDoctorApplication.restore_best(report, restored.append)
        self.assertEqual(restored, [self.checkpoints[0].path])
        metadata = []
        TrainingDoctorApplication.publish_prompt_metadata(report, metadata.append)
        self.assertEqual(metadata[0]["recommended_lora_strength"], report.recommended_strength)
        self.assertEqual(metadata[0]["recommended_trigger"], "mira")
        path = save_report(report, self.root / "doctor.json")
        loaded = load_report(path)
        self.assertEqual(loaded.best_checkpoint, report.best_checkpoint)
        self.assertEqual(loaded.validation_samples[0].metrics, report.validation_samples[0].metrics)
        self.assertEqual(loaded.task, ValidationTask.CHARACTER)

    # {
    # 責務: [test_strength_sweep_finds_a_usable_lower_scale: distinguish checkpoint failure from excessive inference weight]
    # 処理: [evaluate two inference scales for a fixed checkpoint and choose the higher control/fidelity balance]
    # 引数: [self: test case]
    # 戻り値: [None: assertion result]
    # }
    def test_strength_sweep_finds_a_usable_lower_scale(self) -> None:
        evaluator = FakeEvaluator("strength")
        plan = fixed_validation_plan(ValidationTask.STYLE, "brush")
        report = TrainingDoctorApplication(evaluator).evaluate_checkpoints(
            self.checkpoints[:1], plan, strengths=(0.6, 1.0, 1.2)
        )
        self.assertEqual(report.recommended_strength, 0.6)

    # {
    # 責務: [test_trigger_sweep_selects_best_token_and_persistent_overfit_stops_training: verify trigger choice and early-stop callback]
    # 処理: [sweep two trigger candidates, observe two successive multi-signal regressions, and record stop request]
    # 引数: [self: test case]
    # 戻り値: [None: assertion result]
    # }
    def test_trigger_sweep_selects_best_token_and_persistent_overfit_stops_training(self) -> None:
        plan = fixed_validation_plan(
            ValidationTask.CHARACTER,
            "token-a",
            trigger_candidates=("token-a", "token-b"),
            conditions=FixedConditions(seeds=(1,), resolutions=((512, 512),)),
        )
        triggers = FakeEvaluator("trigger")
        trigger_report = TrainingDoctorApplication(triggers).evaluate_checkpoints(
            self.checkpoints[:1], plan, strengths=(0.8,)
        )
        self.assertEqual(trigger_report.recommended_trigger, "token-b")
        self.assertEqual(trigger_report.leakage_score, 0.08)

        stop_reasons = []
        evaluator = FakeEvaluator("best_early")
        policy = EarlyStopPolicy(patience=2, overfit_patience=2, signal_threshold=0.1)
        report = TrainingDoctorApplication(evaluator, stop_reasons.append).evaluate_checkpoints(
            self.checkpoints,
            fixed_validation_plan(ValidationTask.CHARACTER, "mira"),
            strengths=(0.8,),
            policy=policy,
        )
        self.assertEqual(len(report.assessments), 3)
        self.assertIn("multi-signal overfit", report.stop_reason)
        self.assertEqual(stop_reasons, [report.stop_reason])
        self.assertTrue(
            any("trigger-free concept leakage" in item for item in report.assessments[-1].signals)
        )

    # {
    # 責務: [test_invalid_metrics_and_unbounded_evaluations_are_rejected: fail closed on untrusted evaluator output]
    # 処理: [reject out-of-range quality evidence and oversized strength sweeps]
    # 引数: [self: test case]
    # 戻り値: [None: assertion result]
    # }
    def test_invalid_metrics_and_unbounded_evaluations_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ImageMetrics(0.5, 0.5, 0.5, 0.5, 0.5, 1.1, 0.5)
        with self.assertRaises(ValueError):
            TrainingDoctorApplication(FakeEvaluator()).evaluate_checkpoints(
                self.checkpoints[:1],
                fixed_validation_plan(ValidationTask.OBJECT),
                strengths=tuple(range(33)),
            )
        balanced = score_weights_for_task(ValidationTask.CHARACTER)
        fidelity = score_weights_for_task(ValidationTask.CHARACTER, ScorePreset.FIDELITY)
        self.assertGreater(fidelity.fidelity, balanced.fidelity)
        self.assertEqual(fidelity.leakage, balanced.leakage)


if __name__ == "__main__":
    unittest.main()
