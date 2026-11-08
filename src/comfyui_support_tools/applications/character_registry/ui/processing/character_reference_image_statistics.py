from collections.abc import Sequence
from pathlib import Path

from src.comfyui_support_tools.shared.contracts.character_reference_image import (
    CharacterReferenceImage,
)


# {
#   責務: [format_reference_image_statistics: 登録候補画像の件数と元ファイル状態を表示文字列へ整形する]
#   処理: [総数, 元画像の存在数, 学習候補数, 衣装別/混在/未分類数を数えて日本語の一行にする]
#   引数: [images: Character Registryへ登録候補として追加された参照画像]
#   戻り値: [str: 品質推定を含まない画像件数の表示]
# }
def format_reference_image_statistics(images: Sequence[CharacterReferenceImage]) -> str:
    """Format current reference counts without implying dataset quality or training readiness."""
    outfit_count = sum(image.outfit_assignment == "outfit" for image in images)
    mixed_count = sum(image.outfit_assignment == "mixed_custom" for image in images)
    unknown_count = sum(image.outfit_assignment == "unknown" for image in images)
    training_count = sum(image.selected_for_training for image in images)
    available_count = sum(Path(image.source_path).is_file() for image in images)
    return (
        f"登録候補: {len(images)}件 / 元画像あり: {available_count}件 / "
        f"学習候補: {training_count}件 / "
        f"衣装別: {outfit_count}件 / 混在: {mixed_count}件 / 未分類: {unknown_count}件"
    )
