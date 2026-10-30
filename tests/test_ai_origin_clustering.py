import errno
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, PngImagePlugin

from scripts.backend.ai_origin_clustering import (
    AI_LABEL,
    NON_AI_LABEL,
    UNCERTAIN_LABEL,
    ImageOriginResult,
    classify_image,
    copy_clusters,
    discover_images,
    write_manifest,
)
from scripts.backend.ai_origin_detector import AnimeAIDetector


# {
# 責務: [FakeScoreProvider: テスト用AIスコア供給器を提供する]
# フィールド: [状態: テスト用AIスコア供給器を提供する]
# }
class FakeScoreProvider:
    # {
    # 責務: [__init__: 依存と設定値を初期化する]
    # 処理: [1: 依存と設定値を初期化する]
    # 引数: [self, score]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def __init__(self, score):
        self.score = score

    # {
    # 責務: [ai_score: 推論対象画像のAI生成スコアを取得する]
    # 処理: [1: 推論対象画像のAI生成スコアを取得する]
    # 引数: [self, _path]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def ai_score(self, _path):
        return self.score


# {
# 責務: [AIOriginClusteringTests: AI画像分類の境界条件と出力を検証する]
# フィールド: [状態: AI画像分類の境界条件と出力を検証する]
# }
class AIOriginClusteringTests(unittest.TestCase):
    # {
    # 責務: [setUp: テスト用一時ディレクトリと入力画像を準備する]
    # 処理: [1: テスト用一時ディレクトリと入力画像を準備する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def setUp(self):
        scratch_root = Path(
            os.environ.get("KADOKA_TOOLS_TEST_TEMP_ROOT", Path.cwd() / ".tmp-tests")
        )
        scratch_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch_root)
        self.root = Path(self.temporary.name)

    # {
    # 責務: [tearDown: テスト用一時ディレクトリを破棄する]
    # 処理: [1: テスト用一時ディレクトリを破棄する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def tearDown(self):
        self.temporary.cleanup()

    # {
    # 責務: [create_image: テスト用画像を生成する]
    # 処理: [1: テスト用画像を生成する]
    # 引数: [self, path, metadata]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def create_image(self, path, metadata=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        image_info = PngImagePlugin.PngInfo()
        for key, value in (metadata or {}).items():
            image_info.add_text(key, value)
        image = Image.new("RGB", (2, 2), "white")
        if path.suffix.casefold() == ".png":
            image.save(path, pnginfo=image_info)
        else:
            image.save(path)
        return path

    # {
    # 責務: [test_pixiv_metadata_precedes_classifier_and_conflict_is_uncertain: Pixiv metadata優先と矛盾時の保留分類を検証する]
    # 処理: [1: Pixiv metadata優先と矛盾時の保留分類を検証する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def test_pixiv_metadata_precedes_classifier_and_conflict_is_uncertain(self):
        ai_image = self.create_image(self.root / "ai.png")
        ai_image.with_suffix(".json").write_text(json.dumps({"aiType": 2}), encoding="utf-8")
        result = classify_image(ai_image, FakeScoreProvider(0.01), 0.1, 0.9)
        self.assertEqual(result.cluster, AI_LABEL)
        self.assertIsNone(result.confidence)
        self.assertEqual(result.evidence, ("pixiv_json_sidecar",))
        non_ai_image = self.create_image(self.root / "non_ai.png")
        non_ai_image.with_suffix(".json").write_text(json.dumps({"aiType": 1}), encoding="utf-8")
        non_ai_result = classify_image(non_ai_image, FakeScoreProvider(0.99), 0.1, 0.9)
        self.assertEqual(non_ai_result.cluster, NON_AI_LABEL)
        self.assertIsNone(non_ai_result.confidence)
        boolean_image = self.create_image(self.root / "boolean.png")
        boolean_image.with_suffix(".json").write_text(
            json.dumps({"aiType": True}), encoding="utf-8"
        )
        boolean_signal = classify_image(boolean_image, FakeScoreProvider(0.99), 0.1, 0.9)
        self.assertEqual(boolean_signal.cluster, AI_LABEL)
        self.assertEqual(boolean_signal.evidence, ("oss_classifier",))

        conflict_image = self.create_image(self.root / "conflict.png", {"parameters": "prompt"})
        conflict_image.with_suffix(".json").write_text(json.dumps({"aiType": 1}), encoding="utf-8")
        conflict = classify_image(conflict_image, FakeScoreProvider(0.99), 0.1, 0.9)
        self.assertEqual(conflict.cluster, UNCERTAIN_LABEL)
        ordinary_prompt = self.create_image(
            self.root / "ordinary_prompt.png", {"prompt": "portrait"}
        )
        prompt_result = classify_image(ordinary_prompt, FakeScoreProvider(0.01), 0.1, 0.9)
        self.assertEqual(prompt_result.cluster, NON_AI_LABEL)
        self.assertEqual(prompt_result.evidence, ("oss_classifier",))

    # {
    # 責務: [test_classifier_thresholds_produce_three_clusters: 閾値による3分類を検証する]
    # 処理: [1: 閾値による3分類を検証する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def test_classifier_thresholds_produce_three_clusters(self):
        image = self.create_image(self.root / "sample.png")
        self.assertEqual(
            classify_image(image, FakeScoreProvider(0.1), 0.1, 0.9).cluster, NON_AI_LABEL
        )
        self.assertEqual(classify_image(image, FakeScoreProvider(0.9), 0.1, 0.9).cluster, AI_LABEL)
        self.assertEqual(
            classify_image(image, FakeScoreProvider(0.5), 0.1, 0.9).cluster, UNCERTAIN_LABEL
        )

    # {
    # 責務: [test_discovery_is_recursive_and_excludes_output: 再帰列挙と出力先除外を検証する]
    # 処理: [1: 再帰列挙と出力先除外を検証する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def test_discovery_is_recursive_and_excludes_output(self):
        source = self.root / "source"
        self.create_image(source / "nested" / "image.png")
        self.create_image(source / "output" / "old.png")
        (source / "nested" / "readme.txt").write_text("skip", encoding="utf-8")
        images = discover_images(source, recursive=True, excluded_root=source / "output")
        self.assertEqual(
            [path.relative_to(source).as_posix() for path in images], ["nested/image.png"]
        )
        gif_image = self.create_image(source / "nested" / "animated.gif")
        tiff_image = self.create_image(source / "nested" / "scan.tiff")
        images = discover_images(source, recursive=True, excluded_root=source / "output")
        self.assertIn(gif_image, images)
        self.assertIn(tiff_image, images)

    # {
    # 責務: [test_discovery_reports_walk_errors: 読めないサブフォルダーを隠さず報告する]
    # 処理: [1: os.walkのonerror callbackで例外が伝播することを検証する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_discovery_reports_walk_errors(self):
        source = self.root / "source"
        source.mkdir()

        # {
        #   責務: [fail_walk: テスト用にos.walkのエラー通知を発生させる]
        #   処理: [1: onerrorへPermissionErrorを渡す]
        #   引数: [_root, followlinks, onerror]
        #   戻り値: [空のwalk iterator]
        # }
        def fail_walk(_root, *, followlinks, onerror):
            self.assertFalse(followlinks)
            onerror(PermissionError("inaccessible directory"))
            return iter(())

        with mock.patch("scripts.backend.ai_origin_clustering.os.walk", side_effect=fail_walk):
            with self.assertRaisesRegex(PermissionError, "inaccessible directory"):
                discover_images(source, recursive=True)

    # {
    # 責務: [test_copy_preserves_source_and_sidecar_without_overwriting: 元ファイル保全と上書き防止を検証する]
    # 処理: [1: 元ファイル保全と上書き防止を検証する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def test_copy_preserves_source_and_sidecar_without_overwriting(self):
        source = self.root / "source"
        output = self.root / "output"
        image_path = self.create_image(source / "nested" / "image.png")
        image_path.with_suffix(".txt").write_text("caption", encoding="utf-8")
        image_path.with_suffix(".json").write_text('{"source":"expected"}', encoding="utf-8")
        result = ImageOriginResult(image_path, AI_LABEL, 0.99, ("oss_classifier",), "high")
        expected = output / AI_LABEL / "nested" / "image.png"
        expected.parent.mkdir(parents=True)
        expected.write_bytes(b"existing file")
        expected.with_suffix(".json").write_text('{"source":"unrelated"}', encoding="utf-8")
        self.assertEqual(copy_clusters([result], source, output), 1)
        self.assertEqual(image_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        sidecars = list((output / AI_LABEL / "nested").glob("image_*.txt"))
        self.assertEqual(len(sidecars), 1)
        self.assertEqual(sidecars[0].read_text(encoding="utf-8"), "caption")
        copied_json = sidecars[0].with_suffix(".json")
        self.assertTrue(copied_json.is_file())
        self.assertEqual(json.loads(copied_json.read_text(encoding="utf-8"))["source"], "expected")
        self.assertEqual(
            json.loads(expected.with_suffix(".json").read_text(encoding="utf-8"))["source"],
            "unrelated",
        )
        self.assertEqual(len(list(expected.parent.glob("image_*.png"))), 1)
        self.assertEqual(copy_clusters([result], source, output), 0)
        self.assertEqual(len(list(expected.parent.glob("image_*.png"))), 1)

    # {
    # 責務: [test_copy_rolls_back_partial_output: コピー失敗時に今回作ったファイルを戻す]
    # 処理: [1: 2枚目の公開を失敗させ先行出力が除去されることを確認する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_copy_rolls_back_partial_output(self):
        source = self.root / "source"
        output = self.root / "output"
        first_image = self.create_image(source / "first.png")
        second_image = self.create_image(source / "second.png")
        results = [
            ImageOriginResult(path, AI_LABEL, 0.99, ("oss_classifier",), "high")
            for path in (first_image, second_image)
        ]
        from scripts.backend import ai_origin_clustering

        original_copy = ai_origin_clustering._copy_file_atomically
        calls = 0

        # {
        #   責務: [fail_second_copy: 2個目のファイルをテスト用に失敗させる]
        #   処理: [1: 2個目のコピー時にOSErrorを投げる]
        #   引数: [source_path, destination_path, allowed_root]
        #   戻り値: [最初のコピー結果]
        # }
        def fail_second_copy(source_path, destination_path, allowed_root=None):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated copy failure")
            return original_copy(source_path, destination_path, allowed_root)

        with mock.patch(
            "scripts.backend.ai_origin_clustering._copy_file_atomically",
            side_effect=fail_second_copy,
        ):
            with self.assertRaisesRegex(OSError, "simulated copy failure"):
                copy_clusters(results, source, output)
        self.assertEqual(list(output.rglob("*.png")), [])

    # {
    # 責務: [test_copy_falls_back_when_hard_links_are_unsupported: hard link非対応先で安全コピーする]
    # 処理: [1: hard link作成を失敗させ画像とmanifestの代替コピーを確認する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_copy_falls_back_when_hard_links_are_unsupported(self):
        source = self.root / "source"
        output = self.root / "output"
        image_path = self.create_image(source / "image.png")
        result = ImageOriginResult(image_path, AI_LABEL, 0.99, ("oss_classifier",), "high")
        with mock.patch(
            "scripts.backend.ai_origin_clustering.os.link",
            side_effect=OSError(errno.EPERM, "hard links unavailable"),
        ):
            self.assertEqual(copy_clusters([result], source, output), 1)
            manifest = write_manifest([result], output / "manifest.json")
        self.assertTrue((output / AI_LABEL / "image.png").is_file())
        self.assertTrue(manifest.is_file())

    # {
    # 責務: [test_output_cannot_be_inside_input_and_manifest_is_not_overwritten: 出力root制約とmanifestの上書き防止を検証する]
    # 処理: [1: 出力root制約とmanifestの上書き防止を検証する]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def test_output_cannot_be_inside_input_and_manifest_is_not_overwritten(self):
        image_path = self.create_image(self.root / "source" / "sample.png")
        result = ImageOriginResult(image_path, NON_AI_LABEL, 0.01, ("oss_classifier",), "low")
        with self.assertRaises(ValueError):
            copy_clusters([result], self.root / "source", self.root / "source" / "clusters")
        manifest = self.root / "result.json"
        first = write_manifest([result], manifest)
        second = write_manifest([result], manifest)
        self.assertEqual(first, second)
        self.assertEqual(
            json.loads(manifest.read_text(encoding="utf-8"))[0]["cluster"], NON_AI_LABEL
        )

    # {
    # 責務: [test_copy_rejects_symlinked_cluster_directory: symlink出力先による入力外書き込みを防ぐ]
    # 処理: [1: 出力クラスタディレクトリのsymlink検出後にコピーを拒否する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_copy_rejects_symlinked_cluster_directory(self):
        source = self.root / "source"
        output = self.root / "output"
        image_path = self.create_image(source / "sample.png")
        result = ImageOriginResult(image_path, AI_LABEL, 0.99, ("oss_classifier",), "high")
        cluster_directory = output / AI_LABEL
        cluster_directory.mkdir(parents=True)
        original_is_symlink = Path.is_symlink

        # {
        #   責務: [report_cluster_symlink: 出力clusterをsymlinkとして報告する]
        #   処理: [1: 指定cluster pathのみsymlinkと判定する]
        #   引数: [path: 検査するパス]
        #   戻り値: [symlink判定]
        # }
        def report_cluster_symlink(path):
            return path == cluster_directory or original_is_symlink(path)

        with mock.patch.object(Path, "is_symlink", report_cluster_symlink):
            with self.assertRaisesRegex(ValueError, "シンボリックリンク"):
                copy_clusters([result], source, output)

        self.assertFalse((cluster_directory / "sample.png").exists())

    # {
    # 責務: [test_copy_rejects_replaced_source: コピー直前に差し替えられた入力を拒否する]
    # 処理: [1: 開いたsourceとpath上のfile identity不一致を検出する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_copy_rejects_replaced_source(self):
        source = self.root / "source"
        output = self.root / "output"
        image_path = self.create_image(source / "sample.png")
        external_path = self.create_image(self.root / "external.png")
        result = ImageOriginResult(image_path, AI_LABEL, 0.99, ("oss_classifier",), "high")
        original_lstat = Path.lstat

        # {
        #   責務: [report_replaced_source: sourceの差し替え状態をテストする]
        #   処理: [1: sourceのlstatに外部ファイルのidentityを返す]
        #   引数: [path: 検査するパス]
        #   戻り値: [元pathまたは差し替え後pathのstat]
        # }
        def report_replaced_source(path):
            if path == image_path:
                return original_lstat(external_path)
            return original_lstat(path)

        with mock.patch.object(Path, "lstat", report_replaced_source):
            with self.assertRaisesRegex(ValueError, "入力ファイルが差し替えられました"):
                copy_clusters([result], source, output)

        self.assertFalse((output / AI_LABEL / "sample.png").exists())

    # {
    # 責務: [test_concurrent_manifest_writes_reuse_one_result: 同時manifest保存の衝突を防ぐ]
    # 処理: [1: 複数threadから保存し同一manifestパスへ直列化されることを確認する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_concurrent_manifest_writes_reuse_one_result(self):
        image_path = self.create_image(self.root / "source" / "sample.png")
        result = ImageOriginResult(image_path, NON_AI_LABEL, 0.01, ("oss_classifier",), "low")
        manifest_path = self.root / "manifest.json"
        results = []
        errors = []

        # {
        #   責務: [write: 1件のmanifest保存workerを実行する]
        #   処理: [1: manifest保存結果または例外を共有リストへ記録する]
        #   引数: []
        #   戻り値: []
        # }
        def write():
            try:
                results.append(write_manifest([result], manifest_path))
            except Exception as error:
                errors.append(error)

        workers = [threading.Thread(target=write) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(errors, [])
        self.assertEqual(results, [manifest_path, manifest_path])
        self.assertEqual(list(self.root.glob("manifest_*.json")), [])

    # {
    # 責務: [test_frozen_detector_reports_missing_runtime: 凍結版の未対応runtimeを明示する]
    # 処理: [1: 外部プロセスを起動せずruntime不足を通知する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_frozen_detector_reports_missing_runtime(self):
        image_path = self.create_image(self.root / "sample.png")
        with mock.patch.object(sys, "frozen", True, create=True):
            detector = AnimeAIDetector("saltacc/anime-ai-detect", "cpu")
            with self.assertRaisesRegex(RuntimeError, "凍結版にはPyTorch/Transformers"):
                detector.ai_score(image_path)

    # {
    # 責務: [test_detector_caches_pipeline_errors: モデル起動失敗を画像ごとに繰り返さない]
    # 処理: [1: 起動失敗を2度呼び出して生成処理が1回だけ行われることを確認する]
    # 引数: [self]
    # 戻り値: []
    # }
    def test_detector_caches_pipeline_errors(self):
        detector = AnimeAIDetector("local-model", "cpu")
        calls = 0

        # {
        #   責務: [fail_pipeline: 判定モデル初期化失敗をテストする]
        #   処理: [1: RuntimeErrorを送出する]
        #   引数: []
        #   戻り値: [到達しない]
        # }
        def fail_pipeline():
            nonlocal calls
            calls += 1
            raise OSError("model download failed")

        detector._create_pipeline = fail_pipeline
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                detector._load_pipeline()
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()
