import unittest

from src.comfyui_support_tools.applications.character_registry.ui.processing.character_reference_image_training_selection import (
    toggle_reference_image_training_selection,
)
from src.comfyui_support_tools.shared.contracts.character_reference_image import (
    CharacterReferenceImage,
)


# {
#   責務: [CharacterReferenceImageTrainingSelectionTests: 参照画像の学習候補状態切替を検証する]
#   フィールド: [unittest assertions]
# }
class CharacterReferenceImageTrainingSelectionTests(unittest.TestCase):
    # {
    #   責務: [test_mixed_selection_marks_all_selected: 混在選択を一括で学習候補へ含める]
    #   処理: [選択行に未選択画像が含まれる場合は選択行全てを候補へ追加する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_mixed_selection_marks_all_selected(self) -> None:
        images = (
            self._image("a", selected=True),
            self._image("b", selected=False),
            self._image("c", selected=False),
        )

        updated, selected_for_training = toggle_reference_image_training_selection(
            images,
            (0, 1),
        )

        self.assertTrue(selected_for_training)
        self.assertEqual(
            tuple(image.selected_for_training for image in updated),
            (True, True, False),
        )

    # {
    #   責務: [test_all_selected_rows_are_removed_from_training_candidates: 選択済み画像を候補から一括で外す]
    #   処理: [選択行がすべて候補の場合は選択行全てを対象外へ切替える]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_all_selected_rows_are_removed_from_training_candidates(self) -> None:
        images = (self._image("a", selected=True), self._image("b", selected=True))

        updated, selected_for_training = toggle_reference_image_training_selection(
            images,
            (0, 1),
        )

        self.assertFalse(selected_for_training)
        self.assertEqual(
            tuple(image.selected_for_training for image in updated),
            (False, False),
        )

    # {
    #   責務: [test_empty_or_invalid_selection_is_rejected: 空選択と範囲外行を拒否する]
    #   処理: [入力indexが無いまたは画像一覧範囲外ならValueErrorを送出する]
    #   引数: [self: unittest.TestCase]
    #   戻り値: []
    # }
    def test_empty_or_invalid_selection_is_rejected(self) -> None:
        images = (self._image("a"),)

        for selected_indices in ((), (-1,), (1,)):
            with self.subTest(selected_indices=selected_indices):
                with self.assertRaises(ValueError):
                    toggle_reference_image_training_selection(images, selected_indices)

    # {
    #   責務: [_image: test用の参照画像contractを作る]
    #   処理: [SHA-256由来IDと絶対pathを持つ参照画像を返す]
    #   引数: [self: unittest.TestCase, suffix: hash用の文字, selected: 初期選択状態]
    #   戻り値: [CharacterReferenceImage: test fixture]
    # }
    def _image(self, suffix: str, *, selected: bool = False) -> CharacterReferenceImage:
        digest = suffix * 64
        return CharacterReferenceImage(
            image_id=f"sha256-{digest}",
            source_path=f"C:/images/{suffix}.png",
            content_sha256=digest,
            selected_for_training=selected,
        )


if __name__ == "__main__":
    unittest.main()
