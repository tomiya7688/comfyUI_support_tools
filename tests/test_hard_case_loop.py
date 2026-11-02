"""Tests for local Touka failure history, clustering, calibration, and export."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from comfyui_support_tools.shared.hard_case_loop import (
    CandidateEvidence,
    HardCaseFeatures,
    HardCaseRecord,
    HardCaseStore,
    calibrate_confidence,
    cluster_hard_cases,
    compare_model_configs,
    export_active_learning_manifest,
    extract_hard_case_features,
    run_regression_set,
    select_active_learning_samples,
)


# {
#   責務: [HardCaseLoopTests: local hard-case lifecycleとselection metricsを検証する]
#   フィールド: [SQLite temp store and explicit user feedback]
#   処理: [check round-trip, clustering, calibration, regression and export]
# }
class HardCaseLoopTests(unittest.TestCase):
    # {
    #   責務: [_record: deterministic hard-case fixtureを構築する]
    #   処理: [create competing outputs with feedback and normalized multi-axis metrics]
    #   引数: [record_id: stable ID, features: hardness descriptor, material: material tag, failure_tags: tags]
    #   戻り値: [HardCaseRecord: validated failure example]
    # }
    @staticmethod
    def _record(
        record_id: str,
        features: HardCaseFeatures,
        material: str = "cloth",
        failure_tags: tuple[str, ...] = ("blur",),
    ) -> HardCaseRecord:
        return HardCaseRecord(
            record_id=record_id,
            dataset_id="real-regression-v1",
            input_sha256=(record_id.encode().hex() + "0" * 64)[:64],
            media_type="image",
            local_path_reference=f"private-local://examples/{record_id}.png",
            candidates=(
                CandidateEvidence("automatic", 0.8, 0.95),
                CandidateEvidence("conservative", 0.7, 0.55),
                CandidateEvidence("reference", 0.65, 0.4),
            ),
            features=features,
            failure_tags=failure_tags,
            material=material,
            confidence_map_references=(f"maps/{record_id}_confidence.png",),
            selected_candidate="automatic",
            user_preferred_candidate="conservative",
            rejected_candidates=("automatic",),
            feedback_received=True,
            runtime_seconds=1.25,
            peak_vram_mib=512,
            model_version="touka-local-1",
            config_fingerprint="balanced-a1",
            in_regression_set=True,
            metadata=(("lighting", "mixed"),),
        )

    # {
    #   責務: [test_feature_extraction_and_schema_validation: confidence map feature extractionを検証する]
    #   処理: [compute low-confidence coverage and reject malformed numeric features]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_feature_extraction_and_schema_validation(self) -> None:
        stream = io.BytesIO()
        Image.fromarray(np.array([[0, 32], [200, 255]], dtype=np.uint8), "L").save(stream, "PNG")
        features = extract_hard_case_features(stream.getvalue(), (0.9, 0.1, 0.5), 0.2, 0.3, 0.4)
        self.assertEqual(features.low_confidence_area_ratio, 0.5)
        self.assertGreater(features.candidate_disagreement, 0)
        with self.assertRaisesRegex(ValueError, "input_sha256"):
            self._record("bad", features).__class__(
                record_id="bad",
                dataset_id="set",
                input_sha256="not-a-hash",
                media_type="image",
                local_path_reference="local.png",
                candidates=(CandidateEvidence("a", 0.5, 0.5),),
                features=features,
            )

    # {
    #   責務: [test_sqlite_feedback_and_fixed_regression_membership_persist: local storeを検証する]
    #   処理: [round trip privacy references, feedback state, dataset filter and regression membership]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_sqlite_feedback_and_fixed_regression_membership_persist(self) -> None:
        record = self._record("case-a", HardCaseFeatures(0.2, 0.6, 0.7, 0.1, 0.2))
        with tempfile.TemporaryDirectory() as directory:
            store = HardCaseStore(Path(directory) / "hard_cases.sqlite3")
            store.save(record)
            self.assertEqual(store.get("case-a"), record)
            updated = store.record_feedback("case-a", "conservative", ("automatic",))
            self.assertTrue(updated.feedback_received)
            store.set_regression_membership("case-a", False)
            listed = store.list_records(dataset_id="real-regression-v1")
            self.assertEqual(len(listed), 1)
            self.assertTrue(listed[0].feedback_received)
            self.assertFalse(listed[0].in_regression_set)
            self.assertEqual(store.list_records(regression_only=True), ())
            with self.assertRaises(KeyError):
                store.record_feedback("missing", "conservative")

    # {
    #   責務: [test_clustering_sampling_calibration_and_training_export: mining loopを検証する]
    #   処理: [cluster similar cases, rank high-confidence failure, compute ECE and export local manifest]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_clustering_sampling_calibration_and_training_export(self) -> None:
        first = self._record("case-a", HardCaseFeatures(0.2, 0.6, 0.7, 0.1, 0.2))
        near = self._record("case-b", HardCaseFeatures(0.21, 0.58, 0.69, 0.12, 0.22))
        other = self._record(
            "case-c", HardCaseFeatures(0.8, 0.1, 0.05, 0.8, 0.9), "glass", ("reflection",)
        )
        clusters = cluster_hard_cases((other, near, first), radius=0.1)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(
            set(clusters[0].record_ids) | set(clusters[1].record_ids),
            {"case-a", "case-b", "case-c"},
        )
        selected = select_active_learning_samples((first, near, other), 2)
        self.assertEqual(selected[0].record_id, "case-c")
        report = calibrate_confidence((first, near, other), bin_count=5)
        self.assertEqual(report.sample_count, 3)
        self.assertEqual(set(report.high_confidence_errors), {"case-a", "case-b", "case-c"})
        with tempfile.TemporaryDirectory() as directory:
            path = export_active_learning_manifest(selected, Path(directory) / "training.json")
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["privacy"], "local_references_only")
            self.assertEqual(len(document["records"]), 2)
            self.assertNotIn("image_bytes", document["records"][0])

    # {
    #   責務: [test_fixed_regression_runner_compares_top_n_user_preference: model/config regressionを検証する]
    #   処理: [measure top-1/3/5 and catastrophe when a rejected option remains highest ranked]
    #   引数: [self: unittest case]
    #   戻り値: []
    # }
    def test_fixed_regression_runner_compares_top_n_user_preference(self) -> None:
        record = self._record("case-a", HardCaseFeatures(0.2, 0.6, 0.7, 0.1, 0.2))

        # {
        #   責務: [FakeEvaluator: fixed regression用のdeterministic candidate scoresを提供する]
        #   処理: [入力record/model/configに対してテスト用candidate evidenceを返す]
        #   フィールド: []
        #   引数: []
        #   戻り値: [FakeEvaluator instance: HardCaseEvaluator protocol implementation]
        # }
        class FakeEvaluator:
            # {
            #   責務: [evaluate: test-only deterministic model/config候補を返す]
            #   処理: [rank preferred candidate second and preserve confidence separately]
            #   引数: [record: local case, model_version: version, config_fingerprint: config]
            #   戻り値: [tuple[CandidateEvidence, ...]: ranked test outputs]
            # }
            def evaluate(self, record, model_version, config_fingerprint):
                return (
                    CandidateEvidence("automatic", 0.8, 0.9),
                    CandidateEvidence("conservative", 0.85, 0.6),
                    CandidateEvidence("reference", 0.4, 0.5),
                )

        report = run_regression_set((record,), FakeEvaluator(), "touka-local-2", "balanced-b2")
        self.assertEqual(report.sample_count, 1)
        self.assertEqual(report.top1_preference_rate, 1.0)
        self.assertEqual(report.top3_preference_rate, 1.0)
        self.assertEqual(report.catastrophic_failure_count, 0)
        comparisons = compare_model_configs(
            (record,),
            (
                ("touka-local-2", "balanced-b2", FakeEvaluator()),
                ("touka-local-3", "conservative-c1", FakeEvaluator()),
            ),
        )
        self.assertEqual(
            [item.model_version for item in comparisons], ["touka-local-2", "touka-local-3"]
        )
        self.assertEqual(comparisons[0].top1_preference_rate, comparisons[1].top1_preference_rate)


if __name__ == "__main__":
    unittest.main()
