from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .character_id import is_valid_character_id
from .character_outfit_profile import CharacterOutfitProfile
from .character_reference_image import CharacterReferenceImage
from .character_profile_validation import validate_text_tuple
from .character_source_asset import CharacterSourceAsset


# {
#   責務: [_utc_now: CharacterProfileのUTC timestamp defaultを作る]
#   処理: [timezone-awareな現在時刻を返す]
#   引数: []
#   戻り値: [datetime: UTC timestamp]
# }
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# {
#   責務: [CharacterProfile: stable IDを主キーにidentity, outfit割当付きimages, provenanceを保持する]
#   フィールド: [character_id: 表示名に依存しないstable ID, display_name: 表示名, aliases: 別名, core_traits: identity候補, confirmed_core_traits: 確認済みidentity, rejected_traits: 除外候補, default_outfit_id: 既定衣装ID, outfit_profiles: 衣装profile, reference_image_ids: 参照画像ID, reference_images: 元画像pathとSHA-256, provenance: source asset情報, created_at: 作成時刻, updated_at: 更新時刻]
# }
@dataclass(frozen=True)
class CharacterProfile:
    character_id: str
    display_name: str
    aliases: tuple[str, ...] = ()
    core_traits: tuple[str, ...] = ()
    confirmed_core_traits: tuple[str, ...] = ()
    rejected_traits: tuple[str, ...] = ()
    default_outfit_id: str | None = None
    outfit_profiles: tuple[CharacterOutfitProfile, ...] = ()
    reference_image_ids: tuple[str, ...] = ()
    reference_images: tuple[CharacterReferenceImage, ...] = ()
    provenance: tuple[CharacterSourceAsset, ...] = ()
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime | None = None

    # {
    #   責務: [__post_init__: profileのstable ID, 衣装参照, trait, timestampを検証する]
    #   処理: [display name変更時もIDを保ち, 画像割当先/source_image_idsとdefault outfit参照を検証する]
    #   引数: [self: character profile]
    #   戻り値: []
    #   エラー: [ValueError: profile schemaが不正な場合]
    # }
    def __post_init__(self) -> None:
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", self.created_at)
        if not is_valid_character_id(self.character_id):
            raise ValueError("character_idは1〜64文字の小文字英数字と-_で指定してください")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("display_nameを指定してください")
        for field_name in (
            "aliases",
            "core_traits",
            "confirmed_core_traits",
            "rejected_traits",
            "reference_image_ids",
        ):
            validate_text_tuple(field_name, getattr(self, field_name))
        if not isinstance(self.outfit_profiles, tuple) or any(
            not isinstance(outfit, CharacterOutfitProfile) for outfit in self.outfit_profiles
        ):
            raise ValueError("outfit_profilesはCharacterOutfitProfileのtupleで指定してください")
        if not isinstance(self.reference_images, tuple) or any(
            not isinstance(image, CharacterReferenceImage) for image in self.reference_images
        ):
            raise ValueError("reference_imagesはCharacterReferenceImageのtupleで指定してください")
        image_ids = tuple(image.image_id for image in self.reference_images)
        if len(image_ids) != len(set(image_ids)):
            raise ValueError("reference_imagesに同じ画像内容を重複登録できません")
        if self.reference_images and image_ids != self.reference_image_ids:
            raise ValueError("reference_image_idsはreference_imagesと同じ順序で指定してください")
        outfit_ids = tuple(outfit.outfit_id for outfit in self.outfit_profiles)
        if len(outfit_ids) != len(set(outfit_ids)):
            raise ValueError("outfit_profilesのoutfit_idは重複できません")
        outfit_by_id = {outfit.outfit_id: outfit for outfit in self.outfit_profiles}
        for image in self.reference_images:
            if image.outfit_assignment == "outfit":
                outfit = outfit_by_id.get(image.outfit_id or "")
                if outfit is None:
                    raise ValueError("画像のoutfit_idは登録済みoutfit_profilesを参照してください")
                if image.image_id not in outfit.source_image_ids:
                    raise ValueError("割当画像IDをoutfitのsource_image_idsへ含めてください")
        if self.default_outfit_id is not None and self.default_outfit_id not in outfit_ids:
            raise ValueError("default_outfit_idは登録済みoutfit profileを参照してください")
        if (
            not isinstance(self.created_at, datetime)
            or not isinstance(self.updated_at, datetime)
            or self.created_at.utcoffset() != timedelta(0)
            or self.updated_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("created_atとupdated_atはUTCのtimezone-awareで指定してください")
        if not isinstance(self.provenance, tuple) or any(
            not isinstance(asset, CharacterSourceAsset) for asset in self.provenance
        ):
            raise ValueError("provenanceはCharacterSourceAssetのtupleで指定してください")
        if self.updated_at < self.created_at:
            raise ValueError("updated_atはcreated_atより前にできません")
