"""Tests for dataset evidence fusion, boolean extraction and verified transfers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from comfyui_support_tools.shared.dataset_classifier import (
    ClassificationEvidence,
    ClassificationResult,
    DatasetClassifierApplication,
    DatasetQuery,
    QueryCondition,
    QueryGroup,
    SidecarMetadataClassifier,
    StyleEmbeddingClusterer,
    TransferRecord,
    matches_query,
    query_preset,
)


# {
# 責務: [FakeAxisClassifier: return deterministic evidence for one semantic axis]
# フィールド: [axis, claims, calls]
# 処理: [test evidence fusion, query caching and uncertain handling without ML downloads]
# }
class FakeAxisClassifier:
    # {
    # 責務: [__init__: store axis labels and confidence evidence]
    # 処理: [prepare an adapter response and call counter]
    # 引数: [axis: classification axis, claims: label/confidence/source triples]
    # 戻り値: [None: initialized fake classifier]
    # }
    def __init__(self, axis, claims):
        self.axis = axis
        self.claims = claims
        self.calls = 0

    # {
    # 責務: [classify: emit fixture evidence]
    # 処理: [count adapter calls and produce typed evidence records]
    # 引数: [image_path: source image]
    # 戻り値: [tuple[ClassificationEvidence, ...]: axis claims]
    # }
    def classify(self, image_path):
        self.calls += 1
        return tuple(
            ClassificationEvidence(self.axis, label, confidence, source)
            for label, confidence, source in self.claims
        )


# {
# 責務: [DatasetClassifierTests: cover recursive inventory through safe transfer]
# フィールド: [temporary image datasets and local classifier fixtures]
# 処理: [test metadata precedence, cache reuse, query logic, manual labels, and sidecars]
# }
class DatasetClassifierTests(unittest.TestCase):
    # {
    # 責務: [make_dataset: create nested PNG and sidecar fixtures]
    # 処理: [return input root, image path and output path]
    # 引数: [root: isolated temporary workspace]
    # 戻り値: [tuple[Path, Path, Path]: root, source image, output]
    # }
    def make_dataset(self, root):
        source_root = root / "input"
        nested = source_root / "artist" / "series"
        nested.mkdir(parents=True)
        image_path = nested / "hero.png"
        Image.new("RGB", (4, 4), (20, 30, 40)).save(image_path)
        image_path.with_suffix(".txt").write_text("blue hero", encoding="utf-8")
        output = root / "output"
        return source_root, image_path, output

    # {
    # 責務: [test_metadata_precedence_multi_evidence_and_disk_cache: verify normalized classification]
    # 処理: [prefer sidecar labels, retain classifier alternates and reuse stat-fingerprinted cache]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_metadata_precedence_multi_evidence_and_disk_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, image_path, _output = self.make_dataset(Path(temporary))
            image_path.with_suffix(".json").write_text(
                json.dumps({"character": ["hero_a"], "ai_origin": "ai_generated"}),
                encoding="utf-8",
            )
            classifier = FakeAxisClassifier(
                "character", (("hero_a", 0.8, "tagger"), ("hero_b", 0.7, "face_embedding"))
            )
            app = DatasetClassifierApplication()
            app.register("character", classifier)
            metadata = SidecarMetadataClassifier(("character",))
            app.register("character", metadata, name="sidecar", priority=100)
            app.register(
                "ai_origin",
                SidecarMetadataClassifier(("ai_origin",)),
                name="origin_metadata",
                priority=100,
            )
            cache = Path(temporary) / "index.json"
            first = app.classify_folder(root, cache_path=cache)
            second = app.classify_folder(root, cache_path=cache)
            result = first[0]
            self.assertEqual(dict(result.labels)["character"], ("hero_a",))
            self.assertEqual(dict(result.labels)["ai_origin"], ("ai_generated",))
            self.assertEqual(classifier.calls, 1)
            self.assertEqual(second, first)
            self.assertTrue(cache.is_file())
            handoff = app.curator_handoff(first)[0]
            self.assertEqual(handoff["character_ids"], ("hero_a",))
            self.assertEqual(handoff["source_path"], str(image_path.resolve()))
            image_path.with_suffix(".json").write_text(
                json.dumps({"character": ["hero_c"]}), encoding="utf-8"
            )
            refreshed = app.classify_folder(root, cache_path=cache)
            self.assertEqual(dict(refreshed[0].labels)["character"], ("hero_c",))

    # {
    # 責務: [test_disagreement_becomes_uncertain_and_manual_override_is_audited: protect ambiguity]
    # 処理: [retain alternate labels, flag disagreement, then replace with reviewed label]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_disagreement_becomes_uncertain_and_manual_override_is_audited(self):
        with tempfile.TemporaryDirectory() as temporary:
            _root, image, _output = self.make_dataset(Path(temporary))
            app = DatasetClassifierApplication(confidence_threshold=0.6, disagreement_threshold=0.2)
            app.register("situation", FakeAxisClassifier("situation", (("school", 0.8, "tagger"),)))
            app.register("situation", FakeAxisClassifier("situation", (("office", 0.7, "vlm"),)))
            result = app.classify(image)
            self.assertEqual(dict(result.labels)["situation"], ("uncertain",))
            self.assertGreater(dict(result.disagreement)["situation"], 0.2)
            reviewed = app.apply_overrides(
                (result,), {str(image.resolve()): {"situation": ("school",)}}
            )[0]
            self.assertEqual(dict(reviewed.labels)["situation"], ("school",))
            self.assertEqual(reviewed.manual_overrides, (("situation", ("school",)),))
            self.assertEqual(reviewed.evidence[-1].source, "manual_review")
            review_path = Path(temporary) / "reviews.json"
            app.save_review_overrides(review_path, {str(image.resolve()): {"situation": "school"}})
            self.assertEqual(
                app.load_review_overrides(review_path)[str(image.resolve())]["situation"],
                ("school",),
            )

    # {
    # 責務: [test_boolean_queries_support_and_or_not_and_confidence: verify extraction logic]
    # 処理: [match a compound query and exclude one character through NOT]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_boolean_queries_support_and_or_not_and_confidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, image, output = self.make_dataset(Path(temporary))
            app = DatasetClassifierApplication()
            app.register(
                "character", FakeAxisClassifier("character", (("hero_a", 0.95, "tagger"),))
            )
            app.register("situation", FakeAxisClassifier("situation", (("school", 0.85, "vlm"),)))
            app.register(
                "ai_origin", FakeAxisClassifier("ai_origin", (("non_ai", 0.9, "metadata"),))
            )
            result = app.classify(image)
            query = DatasetQuery(
                root,
                QueryGroup(
                    "and",
                    (
                        QueryCondition("character", "contains", "hero_a", 0.8),
                        QueryCondition("situation", "eq", "school"),
                        QueryGroup(
                            "not",
                            (QueryCondition("character", "contains", "hero_b"),),
                        ),
                    ),
                ),
                axes=("character", "situation", "ai_origin"),
                action="copy",
            )
            self.assertTrue(matches_query(query, result))
            records = app.plan_export(query, (result,), output)
            self.assertEqual(len(records), 1)
            self.assertIn("ai_origin=non_ai", records[0].destination.parts)
            self.assertEqual(records[0].destination.name, image.name)
            with self.assertRaises(ValueError):
                app.plan_export(query, (result,), root / "inside-output")
            preset = query_preset(
                "sfw_real_character",
                root,
                {"character": "hero_a"},
            )
            self.assertEqual(preset.axes, ("character", "rating", "ai_origin"))

    # {
    # 責務: [test_copy_move_collision_and_manifest_keep_sidecars_together: validate transfer actions]
    # 処理: [dry-run, collision suffix, verified copy, manifest-only, then copy-before-delete move]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_copy_move_collision_and_manifest_keep_sidecars_together(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, image, output = self.make_dataset(Path(temporary))
            result = ClassificationResult(
                image,
                (("character", ("hero",)),),
                (("character", 0.9),),
                (ClassificationEvidence("character", "hero", 0.9, "test"),),
            )
            query = DatasetQuery(
                root, QueryCondition("character", "eq", "hero"), ("character",), "copy"
            )
            app = DatasetClassifierApplication()
            record = app.plan_export(query, (result,), output)[0]
            self.assertFalse(record.destination.exists())
            copied = app.execute_export((record,), "copy", dry_run=False)
            destination = copied[0].destination
            self.assertTrue(destination.is_file())
            self.assertTrue(destination.with_suffix(".txt").is_file())
            self.assertTrue(image.is_file())
            duplicate = app.execute_export((record,), "copy", dry_run=False)[0].destination
            self.assertEqual(duplicate.stem, "hero_1")
            manifest = root / "manifest.json"
            app.execute_export((record,), "manifest", dry_run=False, manifest_path=manifest)
            self.assertEqual(json.loads(manifest.read_text())["records"][0]["action"], "manifest")
            move_record = record.__class__(
                image,
                output / "move" / image.name,
                "move",
                result.labels,
                result.confidence,
                result.evidence,
            )
            blocked_manifest = root / "existing-manifest.json"
            blocked_manifest.write_text("reserved", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                app.execute_export(
                    (move_record,),
                    "move",
                    dry_run=False,
                    manifest_path=blocked_manifest,
                )
            self.assertTrue(image.is_file())
            self.assertTrue(image.with_suffix(".txt").is_file())
            self.assertFalse(move_record.destination.exists())
            moved = app.execute_export((move_record,), "move", dry_run=False)[0].destination
            self.assertFalse(image.exists())
            self.assertFalse(image.with_suffix(".txt").exists())
            self.assertTrue(moved.exists())
            self.assertTrue(moved.with_suffix(".txt").exists())

    # {
    # 責務: [test_sidecar_targets_participate_in_collision_planning: prevent paired metadata overwrite]
    # 処理: [reserve sidecar paths across files sharing a stem but using different image extensions]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_sidecar_targets_participate_in_collision_planning(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "input"
            root.mkdir()
            png = root / "png" / "hero.png"
            jpg = root / "jpg" / "hero.jpg"
            for image in (png, jpg):
                image.parent.mkdir()
                Image.new("RGB", (2, 2)).save(image)
                image.with_suffix(".txt").write_text(image.suffix, encoding="utf-8")
            output = Path(temporary) / "output"
            records = tuple(
                TransferRecord(
                    image,
                    output / image.name,
                    "copy",
                    (("character", ("hero",)),),
                    (("character", 1.0),),
                    (ClassificationEvidence("character", "hero", 1.0, "test"),),
                )
                for image in (png, jpg)
            )
            app = DatasetClassifierApplication()
            copied = app.execute_export(records, "copy", dry_run=False)
            destinations = [item.destination for item in copied]
            sidecars = [path.with_suffix(".txt") for path in destinations]
            self.assertEqual(len(set(sidecars)), 2)
            self.assertEqual(
                {path.read_text(encoding="utf-8") for path in sidecars}, {".png", ".jpg"}
            )

    # {
    # 責務: [test_inventory_is_recursive_hidden_aware_and_skips_symlinks: validate file discovery]
    # 処理: [skip hidden images and symlinked files by default]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_inventory_is_recursive_hidden_aware_and_skips_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, _image, _output = self.make_dataset(Path(temporary))
            hidden = root / ".private.png"
            Image.new("RGB", (2, 2)).save(hidden)
            try:
                (root / "linked.png").symlink_to(root / "artist" / "series" / "hero.png")
            except OSError:
                self.skipTest("symlink creation is unavailable")
            self.assertEqual(len(DatasetClassifierApplication.inventory(root)), 1)
            self.assertEqual(
                len(DatasetClassifierApplication.inventory(root, include_hidden=True)), 2
            )

    # {
    # 責務: [test_style_embeddings_form_reusable_stable_clusters: verify external style adapter]
    # 処理: [cluster close vectors, retain a separate outlier, and classify fitted members]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_style_embeddings_form_reusable_stable_clusters(self):
        # {
        # 責務: [FixtureEmbeddingProvider: provide deterministic vectors for clustering tests]
        # フィールド: [none: vectors are selected from fixture image names]
        # }
        class FixtureEmbeddingProvider:
            # {
            # 責務: [embed: return a path-keyed fixture vector]
            # 処理: [keep clustering independent from any model package]
            # 引数: [image_path: source image]
            # 戻り値: [tuple[float, ...]: fixture embedding]
            # }
            def embed(self, image_path):
                vectors = {
                    "a.png": (1.0, 0.0, 0.0),
                    "b.png": (0.99, 0.01, 0.0),
                    "c.png": (0.0, 0.0, 1.0),
                }
                return vectors[Path(image_path).name]

        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for name in ("a.png", "b.png", "c.png"):
                path = Path(temporary) / name
                Image.new("RGB", (2, 2)).save(path)
                paths.append(path)
            clusterer = StyleEmbeddingClusterer(FixtureEmbeddingProvider())
            results = clusterer.fit(paths)
            labels = {path.name: item.label for path, item in results.items()}
            self.assertEqual(labels["a.png"], labels["b.png"])
            self.assertNotEqual(labels["b.png"], labels["c.png"])
            self.assertEqual(clusterer.classify(paths[0])[0], results[paths[0].resolve()])


if __name__ == "__main__":
    unittest.main()
