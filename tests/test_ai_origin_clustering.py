import json
import os
import tempfile
import unittest
from pathlib import Path

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


class FakeScoreProvider:
    # {
    #   責務: [FakeScoreProvider: テスト画像ごとの再現可能なスコアを返す]
    #   概要: [ネットワーク・GPUなしで分類境界を検証する]
    # }

    def __init__(self, score):
        # {
        #   責務: [__init__: 固定スコアを設定する]
        #   引数: [self: provider, score: AI生成スコア]
        #   戻り値: []
        # }
        self.score = score

    def ai_score(self, _path):
        # {
        #   責務: [ai_score: テスト用スコアを返す]
        #   引数: [self: provider, _path: 推論対象画像]
        #   戻り値: [設定されたAI生成スコア]
        # }
        return self.score


class AIOriginClusteringTests(unittest.TestCase):
    # {
    #   責務: [AIOriginClusteringTests: 生成元判定と非破壊クラスタ出力を検証する]
    #   概要: [一時画像のみ使い実データや外部モデルを変更・取得しない]
    # }

    def setUp(self):
        # {
        #   責務: [setUp: workspace内に破棄可能なテストディレクトリを作る]
        #   引数: [self: test case]
        #   戻り値: []
        # }
        scratch_root = Path(
            os.environ.get("KADOKA_TOOLS_TEST_TEMP_ROOT", Path.cwd() / ".tmp-tests")
        )
        scratch_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch_root)
        self.root = Path(self.temporary.name)

    def tearDown(self):
        # {
        #   責務: [tearDown: テスト用一時ディレクトリを破棄する]
        #   引数: [self: test case]
        #   戻り値: []
        # }
        self.temporary.cleanup()

    def create_image(self, path, metadata=None):
        # {
        #   責務: [create_image: 判定テスト向けの小さなPNGを生成する]
        #   引数: [self: test case, path: 保存先, metadata: 任意PNG text metadata]
        #   戻り値: [保存先画像]
        # }
        path.parent.mkdir(parents=True, exist_ok=True)
        image_info = PngImagePlugin.PngInfo()
        for key, value in (metadata or {}).items():
            image_info.add_text(key, value)
        Image.new("RGB", (2, 2), "white").save(path, pnginfo=image_info)
        return path

    def test_pixiv_metadata_precedes_classifier_and_conflict_is_uncertain(self):
        # {
        #   責務: [test_pixiv_metadata_precedes_classifier_and_conflict_is_uncertain: 明示metadata優先と矛盾時の保留を確認する]
        #   引数: [self: test case]
        #   戻り値: []
        # }
        ai_image = self.create_image(self.root / "ai.png")
        ai_image.with_suffix(".json").write_text(json.dumps({"aiType": 2}), encoding="utf-8")
        result = classify_image(ai_image, FakeScoreProvider(0.01), 0.1, 0.9)
        self.assertEqual(result.cluster, AI_LABEL)
        self.assertEqual(result.evidence, ("pixiv_json_sidecar",))
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

    def test_classifier_thresholds_produce_three_clusters(self):
        # {
        #   責務: [test_classifier_thresholds_produce_three_clusters: 閾値両側と中間値のクラスタを確認する]
        #   引数: [self: test case]
        #   戻り値: []
        # }
        image = self.create_image(self.root / "sample.png")
        self.assertEqual(
            classify_image(image, FakeScoreProvider(0.1), 0.1, 0.9).cluster, NON_AI_LABEL
        )
        self.assertEqual(classify_image(image, FakeScoreProvider(0.9), 0.1, 0.9).cluster, AI_LABEL)
        self.assertEqual(
            classify_image(image, FakeScoreProvider(0.5), 0.1, 0.9).cluster, UNCERTAIN_LABEL
        )

    def test_discovery_is_recursive_and_excludes_output(self):
        # {
        #   責務: [test_discovery_is_recursive_and_excludes_output: 再帰列挙と出力先除外を確認する]
        #   引数: [self: test case]
        #   戻り値: []
        # }
        source = self.root / "source"
        self.create_image(source / "nested" / "image.png")
        self.create_image(source / "output" / "old.png")
        (source / "nested" / "readme.txt").write_text("skip", encoding="utf-8")
        images = discover_images(source, recursive=True, excluded_root=source / "output")
        self.assertEqual(
            [path.relative_to(source).as_posix() for path in images], ["nested/image.png"]
        )

    def test_copy_preserves_source_and_sidecar_without_overwriting(self):
        # {
        #   責務: [test_copy_preserves_source_and_sidecar_without_overwriting: 元画像を残してsidecarと衝突回避コピーを確認する]
        #   引数: [self: test case]
        #   戻り値: []
        # }
        source = self.root / "source"
        output = self.root / "output"
        image_path = self.create_image(source / "nested" / "image.png")
        image_path.with_suffix(".txt").write_text("caption", encoding="utf-8")
        result = ImageOriginResult(image_path, AI_LABEL, 0.99, ("oss_classifier",), "high")
        expected = output / AI_LABEL / "nested" / "image.png"
        expected.parent.mkdir(parents=True)
        expected.write_bytes(b"existing file")
        self.assertEqual(copy_clusters([result], source, output), 1)
        self.assertEqual(image_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        sidecars = list((output / AI_LABEL / "nested").glob("image_*.txt"))
        self.assertEqual(len(sidecars), 1)
        self.assertEqual(sidecars[0].read_text(encoding="utf-8"), "caption")
        self.assertEqual(len(list(expected.parent.glob("image_*.png"))), 1)

    def test_output_cannot_be_inside_input_and_manifest_is_not_overwritten(self):
        # {
        #   責務: [test_output_cannot_be_inside_input_and_manifest_is_not_overwritten: 出力rootとmanifestの上書き保護を確認する]
        #   引数: [self: test case]
        #   戻り値: []
        # }
        image_path = self.create_image(self.root / "source" / "sample.png")
        result = ImageOriginResult(image_path, NON_AI_LABEL, 0.01, ("oss_classifier",), "low")
        with self.assertRaises(ValueError):
            copy_clusters([result], self.root / "source", self.root / "source" / "clusters")
        manifest = self.root / "result.json"
        first = write_manifest([result], manifest)
        second = write_manifest([result], manifest)
        self.assertNotEqual(first, second)
        self.assertEqual(
            json.loads(manifest.read_text(encoding="utf-8"))[0]["cluster"], NON_AI_LABEL
        )


if __name__ == "__main__":
    unittest.main()
