import unittest

from scripts.backend.embedded_random_image import EmbeddedRandomImage
from src.comfyui_support_tools.shared.contracts.feature_settings import FeatureSettings


# {
#   責務: [EmbeddedRandomImageSettingsTests: Random Image設定契約のテスト]
# フィールド: [case: settings contract invariants under test]
#   処理: [設定snapshotの適用と不正な設定IDや型の拒否を検証する]
# }
class EmbeddedRandomImageSettingsTests(unittest.TestCase):
    # {
    #   責務: [test_feature_settings_are_applied_as_a_snapshot: snapshot適用と単回適用を検証する]
    #   処理: [予約値がgeneratorへ適用され, 消費後に再適用されないことを確認する]
    #   引数: [self: unittest instance]
    #   戻り値: []
    # }
    def test_feature_settings_are_applied_as_a_snapshot(self):
        generator = EmbeddedRandomImage()
        generator._log = lambda _message: None
        settings = FeatureSettings(
            "generation.random_image",
            {"output_dir": "output/new", "steps": 28},
        )

        generator.queue_settings_update(settings)

        self.assertTrue(generator._apply_pending_settings())
        self.assertEqual(generator.output_dir, "output/new")
        self.assertEqual(generator.steps, 28)
        self.assertFalse(generator._apply_pending_settings())

    # {
    #   責務: [test_wrong_feature_id_is_rejected: 異なるfeature設定の拒否を検証する]
    #   処理: [generation.random_image以外の設定IDが予約されないことを確認する]
    #   引数: [self: unittest instance]
    #   戻り値: []
    # }
    def test_wrong_feature_id_is_rejected(self):
        generator = EmbeddedRandomImage()
        settings = FeatureSettings("generation.other", {"steps": 10})

        with self.assertRaisesRegex(ValueError, "unsupported settings feature"):
            generator.queue_settings_update(settings)

        self.assertFalse(generator._apply_pending_settings())

    # {
    #   責務: [test_mapping_is_not_accepted_instead_of_feature_settings: 通常mappingの拒否を検証する]
    #   処理: [FeatureSettings以外のmappingが予約されないことを確認する]
    #   引数: [self: unittest instance]
    #   戻り値: []
    # }
    def test_mapping_is_not_accepted_instead_of_feature_settings(self):
        generator = EmbeddedRandomImage()

        with self.assertRaisesRegex(TypeError, "FeatureSettings"):
            generator.queue_settings_update({"steps": 10})


if __name__ == "__main__":
    unittest.main()
