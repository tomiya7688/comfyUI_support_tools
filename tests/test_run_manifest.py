"""Run manifest provenance, privacy, migration, replay, and adapter tests."""

import argparse
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from comfyui_support_tools.shared.contracts.job_contracts import JobSnapshot
from comfyui_support_tools.shared.contracts.run_manifest import (
    ArtifactReference,
    ComponentVersion,
    PrivacyMode,
    ReproducibilityLevel,
    RunDecision,
    RunLineage,
    RunManifestEvent,
    RunStatus,
)
from comfyui_support_tools.shared.run_manifest import (
    JsonLineRunEventStore,
    JsonRunManifestStore,
    add_run_manifest_cli_commands,
    capture_artifact_reference,
    compare_run_manifests,
    create_run_manifest,
    create_run_manifest_event,
    create_run_manifest_for_job,
    finish_run_manifest,
    generate_random_seed,
    manifest_replay_request,
    migrate_run_manifest_payload,
    run_manifest_cli_result,
    run_manifest_to_dict,
)


# {
#   責務: [RunManifestTests: run provenance、privacy、JSON/JSONL、migration、replay/compare CLIを検証する]
#   フィールド: [temporary manifest directory、deterministic run helper]
# }
class RunManifestTests(unittest.TestCase):
    # {
    #   責務: [test_job_snapshot_adapter_records_stable_job_identity: Job Queue snapshotからmanifest identityを引き継ぐ]
    #   処理: [1: queued JobSnapshotを作る 2: adapterでmanifestを生成する 3: job/run ID結合を確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_job_snapshot_adapter_records_stable_job_identity(self):
        job = JobSnapshot(
            "job-123",
            "image.generate",
            "Generate",
            "queued",
            None,
            100.0,
            None,
            None,
            operation_id="operation-456",
        )
        manifest = create_run_manifest_for_job(
            job, "image.generate", "1.2.0", "settings-v3", run_id="run-123"
        )
        self.assertEqual(manifest.job_id, job.id)
        self.assertEqual(manifest.run_id, "run-123")

    # {
    #   責務: [_manifest: sample running manifestを同じ引数で構築する]
    #   処理: [1: sample refs/settings/versions/lineageを渡す 2: optional privacy/run IDを適用する]
    #   引数: [run_id: stable test ID, privacy: field mode mapping]
    #   戻り値: [manifest: running RunManifest]
    # }
    def _manifest(self, run_id="run-test", privacy=None):
        return create_run_manifest(
            "image.generate",
            "1.2.0",
            "settings-v3",
            input_refs=(ArtifactReference("input-1", "file:///image.png", 20, "abc"),),
            resolved_settings={"prompt": "secret prompt", "steps": 20, "workflow": {"nodes": 2}},
            random_seeds={"primary": 31415},
            random_selections={"frame_timestamp": 12.5, "candidate": "input-1"},
            component_versions=(
                ComponentVersion("backend", "2.1"),
                ComponentVersion("model", "model-v5"),
            ),
            environment={"device": "cuda:0", "driver": "550"},
            reproducibility=ReproducibilityLevel.BEST_EFFORT,
            privacy_modes=privacy,
            user_overrides={"steps": 20},
            lineage=RunLineage(parent_run_id="run-parent", retry_of_run_id="run-older"),
            run_id=run_id,
            job_id="job-source-123",
            started_at=100.0,
        )

    # {
    #   責務: [test_json_manifest_round_trip_and_integrity: atomic JSON storage preserves full run provenance and checks digest]
    #   処理: [1: manifestをfinish/save/loadする 2: equalityとtamper rejectionを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_json_manifest_round_trip_and_integrity(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JsonRunManifestStore(Path(temp))
            running = self._manifest()
            completed = finish_run_manifest(
                running,
                RunStatus.FAILED,
                output_artifacts=(ArtifactReference("output-1", "artifacts/out.png", 100),),
                warnings=("fallback used",),
                errors=("backend timeout",),
                decisions=(
                    RunDecision("candidate-1", "selection", "rejected", "low score", "x", 0.2),
                ),
                selected_candidate_refs=("candidate-2",),
                rejected_candidate_refs=("candidate-1",),
                repair_history=(RunDecision("repair-1", "retry", "applied", "reduce batch"),),
                finished_at=120.0,
            )
            reference = store.save(completed)
            self.assertEqual(Path(reference).name, "run-test.json")
            self.assertEqual(store.load("run-test"), completed)
            self.assertEqual(store.load("run-test").job_id, "job-source-123")
            path = Path(reference)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["manifest"]["application_version"] = "tampered"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest"):
                store.load("run-test")
            envelope["manifest"]["status"] = "unknown-status"
            payload = json.dumps(
                envelope["manifest"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            envelope["manifest_sha256"] = hashlib.sha256(payload).hexdigest()
            path.write_text(json.dumps(envelope), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "payload"):
                store.load("run-test")

    # {
    #   責務: [test_privacy_policy_hashes_summarizes_omits_and_blocks_redacted_replay: privacy modesをfield別に適用する]
    #   処理: [1: settings/environment/overridesへmodeを適用する 2: none/hash時にreplayを拒否する]
    #   引数: []
    #   戻り値: []
    # }
    def test_privacy_policy_hashes_summarizes_omits_and_blocks_redacted_replay(self):
        manifest = self._manifest(
            privacy={
                "settings.prompt": PrivacyMode.NONE,
                "settings.workflow": PrivacyMode.HASH,
                "environment": PrivacyMode.SUMMARY,
                "user_overrides": PrivacyMode.NONE,
                "errors": PrivacyMode.NONE,
                "candidate_ref": PrivacyMode.NONE,
                "artifact_uri": PrivacyMode.NONE,
                "artifact_hash": PrivacyMode.NONE,
                "artifact_id": PrivacyMode.HASH,
                "random_seeds.primary": PrivacyMode.HASH,
            }
        )
        settings = dict(manifest.resolved_settings)
        self.assertNotIn("prompt", settings)
        self.assertEqual(settings["workflow"].keys(), {"sha256"})
        self.assertEqual(dict(manifest.environment)["device"], "cuda:0")
        self.assertEqual(manifest.user_overrides, ())
        self.assertIn("sha256", dict(manifest.random_seeds)["primary"])
        self.assertEqual(manifest.input_refs[0].uri, "")
        self.assertEqual(manifest.input_refs[0].sha256, "")
        self.assertTrue(manifest.input_refs[0].artifact_id.startswith("sha256:"))
        with self.assertRaisesRegex(ValueError, "redacted"):
            manifest_replay_request(manifest)
        filtered_result = finish_run_manifest(
            manifest,
            RunStatus.FAILED,
            errors=("private path /users/me/image.png",),
            selected_candidate_refs=("private-candidate",),
        )
        self.assertEqual(filtered_result.errors, ())
        self.assertEqual(filtered_result.selected_candidate_refs, ())
        full = self._manifest()
        replay = manifest_replay_request(full)
        self.assertEqual(replay.application_id, "image.generate")
        self.assertEqual(dict(replay.random_seeds), {"primary": 31415})
        self.assertEqual(dict(replay.resolved_settings)["prompt"], "secret prompt")

    # {
    #   責務: [test_input_hash_seed_and_actual_selection_are_recorded: configurable artifact hashing/generated seed/actual sample time are captured]
    #   処理: [1: bounded content hash referenceを作る 2: seedを生成する 3: random selection metadataをmanifestへ記録する]
    #   引数: []
    #   戻り値: []
    # }
    def test_input_hash_seed_and_actual_selection_are_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image.png"
            image.write_bytes(b"pixels")
            reference = capture_artifact_reference(image, hash_content=True)
            self.assertEqual(reference.size_bytes, 6)
            self.assertEqual(len(reference.sha256), 64)
            seed = generate_random_seed(32)
            self.assertGreaterEqual(seed, 0)
            self.assertLess(seed, 2**32)
            manifest = create_run_manifest(
                "video.analyze",
                "2.0",
                "schema-1",
                input_refs=(reference,),
                random_seeds={"sampling": seed},
                random_selections={
                    "requested_timestamp": 10.0,
                    "actual_timestamp": 10.04,
                    "pts": 250,
                    "time_base": "1/25",
                },
            )
            selection = dict(manifest.random_selections)
            self.assertEqual(selection["actual_timestamp"], 10.04)
            self.assertEqual(selection["pts"], 250)
            self.assertEqual(dict(manifest.random_seeds)["sampling"], seed)
            for invalid_limit in (-1, True, 1.5):
                with self.subTest(invalid_limit=invalid_limit), self.assertRaises(ValueError):
                    capture_artifact_reference(image, hash_limit_bytes=invalid_limit)

    # {
    #   責務: [test_hash_capture_rejects_artifact_replaced_during_read: hash中のpath差し替えを検知する]
    #   処理: [1: open後にpathを別inodeへ置換する 2: snapshot captureが不整合を拒否することを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_hash_capture_rejects_artifact_replaced_during_read(self):
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "image.png"
            replacement = Path(temp) / "replacement.png"
            image.write_bytes(b"original")
            original_open = os.open
            replaced = False

            # {
            #   責務: [open_then_replace: descriptorを開いた直後にartifact pathを入れ替える]
            #   処理: [1: 元fileをopenする 2: pathをreplacement inodeへrenameする]
            #   引数: [path: file path, flags: OS open flags]
            #   戻り値: [descriptor: 元file descriptor]
            # }
            def open_then_replace(path, flags):
                nonlocal replaced
                descriptor = original_open(path, flags)
                if Path(path) == image and not replaced:
                    replacement.write_bytes(b"changed!")
                    replacement.replace(image)
                    replaced = True
                return descriptor

            with patch(
                "comfyui_support_tools.shared.run_manifest.os.open",
                side_effect=open_then_replace,
            ):
                with self.assertRaisesRegex(OSError, "artifact changed"):
                    capture_artifact_reference(image, hash_content=True)

    # {
    #   責務: [test_jsonl_event_store_orders_progress_and_applies_privacy: event journal preserves order and privacy-filtered payload]
    #   処理: [1: out-of-order eventsをappendする 2: orderとredactionを確認する 3: duplicate sequenceを拒否する]
    #   引数: []
    #   戻り値: []
    # }
    def test_jsonl_event_store_orders_progress_and_applies_privacy(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JsonLineRunEventStore(Path(temp))
            later = create_run_manifest_event(
                "run-log",
                2,
                "completed",
                {"status": "ok", "large": "do not retain"},
                privacy_modes={"event.large": PrivacyMode.NONE},
                created_at=12.0,
            )
            earlier = RunManifestEvent("run-log", 1, 11.0, "started", (("seed", 5),))
            store.append(earlier)
            store.append(later)
            events = store.load("run-log")
            self.assertEqual([item.sequence for item in events], [1, 2])
            self.assertEqual(dict(events[1].payload), {"status": "ok"})
            with self.assertRaisesRegex(ValueError, "increase"):
                store.append(earlier)
            with self.assertRaisesRegex(ValueError, "invalid"):
                create_run_manifest_event("run-log", True, "bad-sequence")

    # {
    #   責務: [test_schema_v0_migrates_and_compare_detects_relevant_differences: additive schema v0 loads and run compare reports settings/version delta]
    #   処理: [1: v0 payloadをmigrationする 2: JSON loadで復元する 3: second runを比較する]
    #   引数: []
    #   戻り値: []
    # }
    def test_schema_v0_migrates_and_compare_detects_relevant_differences(self):
        with tempfile.TemporaryDirectory() as temp:
            first = self._manifest("run-v0")
            payload = run_manifest_to_dict(first)
            payload["schema_version"] = 0
            for field in (
                "random_selections",
                "component_versions",
                "environment",
                "selected_candidate_refs",
                "rejected_candidate_refs",
                "repair_history",
                "user_overrides",
                "lineage",
                "provenance",
                "privacy_modes",
                "reproducibility",
                "job_id",
            ):
                payload.pop(field, None)
            self.assertEqual(migrate_run_manifest_payload(payload)["schema_version"], 2)
            path = Path(temp) / "run-v0.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            restored = JsonRunManifestStore(Path(temp)).load("run-v0")
            self.assertEqual(restored.reproducibility, ReproducibilityLevel.BEST_EFFORT)
            self.assertEqual(restored.job_id, "")
            version_one = run_manifest_to_dict(first)
            version_one["schema_version"] = 1
            version_one.pop("job_id")
            self.assertEqual(migrate_run_manifest_payload(version_one)["schema_version"], 2)
            second = create_run_manifest(
                "image.generate",
                "1.3.0",
                "settings-v3",
                resolved_settings={"prompt": "different", "steps": 20},
                random_seeds={"primary": 31415},
                run_id="run-v2",
                started_at=101.0,
            )
            changed = {item.field_path for item in compare_run_manifests(first, second)}
            self.assertIn("application_version", changed)
            self.assertIn("resolved_settings", changed)

    # {
    #   責務: [test_common_cli_show_replay_compare_commands: run subcommands load/show/replay/compare manifests]
    #   処理: [1: two manifestsを書き込む 2: CLI commandsをparseしてaction結果を確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_common_cli_show_replay_compare_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JsonRunManifestStore(Path(temp))
            first = self._manifest("run-one")
            second = create_run_manifest(
                "image.generate",
                "1.2.0",
                "settings-v3",
                resolved_settings={"prompt": "new"},
                run_id="run-two",
                started_at=110.0,
            )
            store.save(first)
            store.save(second)
            parser = argparse.ArgumentParser()
            add_run_manifest_cli_commands(parser.add_subparsers(dest="command", required=True))
            show = parser.parse_args(["run", "show", str(Path(temp) / "run-one.json")])
            self.assertEqual(run_manifest_cli_result(show)["run_id"], "run-one")
            replay = parser.parse_args(["run", "replay", str(Path(temp) / "run-one.json")])
            self.assertEqual(run_manifest_cli_result(replay)["source_run_id"], "run-one")
            compare = parser.parse_args(
                [
                    "run",
                    "compare",
                    str(Path(temp) / "run-one.json"),
                    str(Path(temp) / "run-two.json"),
                ]
            )
            self.assertTrue(run_manifest_cli_result(compare)["differences"])

    # {
    #   責務: [test_image_video_dataset_runs_share_persistent_manifest_schema: image/video/dataset representative runsを同じstore/contractへ保存する]
    #   処理: [1: 各application runを作る 2: media timing/selected subsetを保存する 3: atomic JSONから全て復元する]
    #   引数: []
    #   戻り値: []
    # }
    def test_image_video_dataset_runs_share_persistent_manifest_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JsonRunManifestStore(Path(temp))
            examples = (
                create_run_manifest(
                    "image.generate",
                    "1.0",
                    "image-settings-v1",
                    resolved_settings={"backend": "comfyui", "steps": 24},
                    random_seeds={"generation": 123},
                    component_versions=(ComponentVersion("backend", "comfyui-0.3"),),
                    run_id="image-run",
                ),
                create_run_manifest(
                    "video.analyze",
                    "1.0",
                    "video-settings-v1",
                    input_refs=(ArtifactReference("video", "data/input.mp4", 4096),),
                    random_selections={
                        "requested_timestamp": 4.0,
                        "actual_timestamp": 4.04,
                        "pts": 101,
                        "time_base": "1/25",
                    },
                    reproducibility=ReproducibilityLevel.BEST_EFFORT,
                    run_id="video-run",
                ),
                create_run_manifest(
                    "dataset.rank",
                    "1.0",
                    "dataset-settings-v2",
                    input_refs=(ArtifactReference("dataset", "data/dataset.jsonl", 8192),),
                    random_seeds={"sampling": 987},
                    random_selections={
                        "selected_files": ["a.png", "c.png"],
                        "rejected_files": ["b.png"],
                    },
                    reproducibility=ReproducibilityLevel.DETERMINISTIC,
                    run_id="dataset-run",
                ),
            )
            for manifest in examples:
                finished = finish_run_manifest(
                    manifest, RunStatus.SUCCEEDED, finished_at=manifest.started_at + 1
                )
                store.save(finished)
                self.assertEqual(store.load(manifest.run_id), finished)
            video = store.load("video-run")
            self.assertEqual(dict(video.random_selections)["actual_timestamp"], 4.04)
            dataset = store.load("dataset-run")
            self.assertEqual(dict(dataset.random_selections)["selected_files"], ["a.png", "c.png"])


if __name__ == "__main__":
    unittest.main()
