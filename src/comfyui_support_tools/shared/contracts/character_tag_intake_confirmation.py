from dataclasses import dataclass

from .character_outfit_profile import CharacterOutfitProfile
from .character_profile_validation import validate_text_tuple


# {
#   責務: [CharacterTagIntakeConfirmation: 手動確認済みのidentity/outfit分類を保持する]
#   フィールド: [confirmed_identity_traits: 登録するidentity, rejected_traits: 明示的に除外した候補, outfit_profiles: 確認済み衣装, default_outfit_id: 既定衣装]
# }
@dataclass(frozen=True)
class CharacterTagIntakeConfirmation:
    """Represent manually accepted and rejected Character Registry tags."""

    confirmed_identity_traits: tuple[str, ...]
    rejected_traits: tuple[str, ...] = ()
    outfit_profiles: tuple[CharacterOutfitProfile, ...] = ()
    default_outfit_id: str | None = None

    # {
    #   責務: [__post_init__: confirmation内容が手動確認済みのprofile候補であることを検証する]
    #   処理: [trait tuple, outfit type/confirmation, outfit ID重複, default outfit参照を検証する]
    #   引数: [self: intake confirmation]
    #   戻り値: []
    #   エラー: [ValueError: 未確認または不正なtrait/outfitが含まれる場合]
    # }
    def __post_init__(self) -> None:
        """Reject invalid, duplicate, or contradictory confirmed traits."""
        validate_text_tuple("confirmed_identity_traits", self.confirmed_identity_traits)
        validate_text_tuple("rejected_traits", self.rejected_traits)
        if len(set(self.confirmed_identity_traits)) != len(self.confirmed_identity_traits):
            raise ValueError("confirmed_identity_traitsは重複できません")
        if len(set(self.rejected_traits)) != len(self.rejected_traits):
            raise ValueError("rejected_traitsは重複できません")
        if set(self.confirmed_identity_traits).intersection(self.rejected_traits):
            raise ValueError("同じtraitをconfirmedとrejectedの両方には指定できません")
        if not isinstance(self.outfit_profiles, tuple) or any(
            not isinstance(outfit, CharacterOutfitProfile) or not outfit.user_confirmed
            for outfit in self.outfit_profiles
        ):
            raise ValueError(
                "outfit_profilesはuser_confirmed=TrueのCharacterOutfitProfile tupleで指定してください"
            )
        outfit_ids = tuple(outfit.outfit_id for outfit in self.outfit_profiles)
        if len(set(outfit_ids)) != len(outfit_ids):
            raise ValueError("outfit_idは重複できません")
        rejected_traits = set(self.rejected_traits)
        if any(
            rejected_traits.intersection(
                (
                    *outfit.outerwear_traits,
                    *outfit.garment_traits,
                    *outfit.innerwear_traits,
                    *outfit.accessory_traits,
                )
            )
            for outfit in self.outfit_profiles
        ):
            raise ValueError("同じoutfit traitをconfirmedとrejectedの両方には指定できません")
        if self.default_outfit_id is not None and self.default_outfit_id not in outfit_ids:
            raise ValueError("default_outfit_idは確認済みoutfit_profiles内に指定してください")
