from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .character_id import is_valid_character_id
from .character_profile_validation import validate_text_tuple


# {
#   責務: [CharacterOutfitProfile: Character内の衣装差分とvisibility metadataを保持する]
#   フィールド: [outfit_id: 安定ID, name: 表示名, aliases: 別名, outerwear_traits: 上着候補, garment_traits: 衣服候補, accessory_traits: 装飾候補, innerwear_traits: 内側衣装候補, visibility_rules: 条件付き表示ルール, source_image_ids: 参照画像ID, confidence: 推定信頼度, user_confirmed: 手動確認状態]
# }
@dataclass(frozen=True)
class CharacterOutfitProfile:
    outfit_id: str
    name: str
    aliases: tuple[str, ...] = ()
    outerwear_traits: tuple[str, ...] = ()
    garment_traits: tuple[str, ...] = ()
    accessory_traits: tuple[str, ...] = ()
    innerwear_traits: tuple[str, ...] = ()
    visibility_rules: tuple[str, ...] = ()
    source_image_ids: tuple[str, ...] = ()
    confidence: float | None = None
    user_confirmed: bool = False

    # {
    #   責務: [__post_init__: outfit profileの識別子と内容の境界を検証する]
    #   処理: [ID, name, text tuple, confidence, confirmation flagを検査する]
    #   引数: [self: outfit profile]
    #   戻り値: []
    #   エラー: [ValueError: fieldがschema条件を満たさない場合]
    # }
    def __post_init__(self) -> None:
        if not is_valid_character_id(self.outfit_id):
            raise ValueError("outfit_idは1〜64文字の小文字英数字と-_で指定してください")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("outfit nameを指定してください")
        for field_name in (
            "aliases",
            "outerwear_traits",
            "garment_traits",
            "accessory_traits",
            "innerwear_traits",
            "visibility_rules",
            "source_image_ids",
        ):
            validate_text_tuple(field_name, getattr(self, field_name))
        if self.confidence is not None and (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (float, int))
            or not isfinite(self.confidence)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("confidenceは有限の0.0〜1.0の数値で指定してください")
        if not isinstance(self.user_confirmed, bool):
            raise ValueError("user_confirmedはboolで指定してください")
