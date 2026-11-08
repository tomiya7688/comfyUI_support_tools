from collections.abc import Sequence
from dataclasses import replace

from src.comfyui_support_tools.shared.contracts.character_reference_image import (
    CharacterReferenceImage,
)


# {
#   責務: [toggle_reference_image_training_selection: 選択された参照画像の学習候補状態をまとめて反転する]
#   処理: [選択行の一部でも未選択なら全て候補へ追加し, 全て選択済みなら全て候補から外す]
#   引数: [images: 登録候補画像, selected_indices: UIで選択された行index]
#   戻り値: [tuple[tuple[CharacterReferenceImage, ...], bool]: 更新画像と変更後の選択状態]
#   エラー: [ValueError: 選択行が空または画像index範囲外の場合]
# }
def toggle_reference_image_training_selection(
    images: Sequence[CharacterReferenceImage],
    selected_indices: Sequence[int],
) -> tuple[tuple[CharacterReferenceImage, ...], bool]:
    if not selected_indices:
        raise ValueError("学習候補を変更する参照画像を選択してください")
    if any(
        not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(images)
        for index in selected_indices
    ):
        raise ValueError("選択された参照画像indexが範囲外です")

    should_select = any(not images[index].selected_for_training for index in selected_indices)
    updated_images = list(images)
    for index in set(selected_indices):
        updated_images[index] = replace(
            updated_images[index],
            selected_for_training=should_select,
        )
    return tuple(updated_images), should_select
