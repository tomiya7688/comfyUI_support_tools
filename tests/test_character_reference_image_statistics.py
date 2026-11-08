import tempfile
import unittest
from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.ui.processing.character_reference_image_statistics import (
    format_reference_image_statistics,
)
from src.comfyui_support_tools.shared.contracts.character_reference_image import (
    CharacterReferenceImage,
)


# {
#   責務: [CharacterReferenceImageStatisticsTests: 登録候補画像統計の件数と元画像状態を検証する]
#   フィールド: [unittest assertions]
# }
class CharacterReferenceImageStatisticsTests(unittest.TestCase):
    # {
    #   責務: [test_empty_images_show_zero_counts: 空の登録候補を0件として表示する]
    #   処理: [空tupleを渡し全ての件数が0になることを確認する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_empty_images_show_zero_counts(self) -> None:
        self.assertEqual(
            format_reference_image_statistics(()),
            "登録候補: 0件 / 元画像あり: 0件 / 衣装別: 0件 / 混在: 0件 / 未分類: 0件",
        )

    # {
    #   責務: [test_statistics_count_assignments_and_missing_source_files: 割当分類と元画像の有無を別々に数える]
    #   処理: [実在/欠落pathと各割当stateを混在させ, 統計の内訳を確認する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_statistics_count_assignments_and_missing_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "reference.png"
            source_path.write_bytes(b"image")
            images = (
                CharacterReferenceImage(
                    image_id=f"sha256-{'a' * 64}",
                    source_path=str(source_path),
                    content_sha256="a" * 64,
                    outfit_assignment="outfit",
                    outfit_id="school",
                ),
                CharacterReferenceImage(
                    image_id=f"sha256-{'b' * 64}",
                    source_path=str(Path(temporary_directory) / "missing.png"),
                    content_sha256="b" * 64,
                    outfit_assignment="mixed_custom",
                ),
                CharacterReferenceImage(
                    image_id=f"sha256-{'c' * 64}",
                    source_path=str(source_path),
                    content_sha256="c" * 64,
                ),
            )

            statistics = format_reference_image_statistics(images)

        self.assertEqual(
            statistics,
            "登録候補: 3件 / 元画像あり: 2件 / 衣装別: 1件 / 混在: 1件 / 未分類: 1件",
        )


if __name__ == "__main__":
    unittest.main()
