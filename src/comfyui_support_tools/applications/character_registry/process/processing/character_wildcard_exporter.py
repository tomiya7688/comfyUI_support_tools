from __future__ import annotations

from pathlib import PurePosixPath

from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile


# {
#   責務: [_format_confirmed_traits: 確認済みtraitを安全なwildcard本文へ整形する]
#   処理: [空白をtrimし, 重複を除き, wildcard構文を含むtraitを拒否する]
#   引数: [traits: 整形対象trait, field_name: エラー表示用field名]
#   戻り値: [tuple[str, ...]: 順序を保った一意のtrait]
#   エラー: [ValueError: wildcard構文または改行を含むtraitがある場合]
# }
def _format_confirmed_traits(traits: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    formatted_traits: list[str] = []
    seen_traits: set[str] = set()
    for trait in traits:
        normalized_trait = trait.strip()
        if any(token in normalized_trait for token in ("__", "{", "}", "\n", "\r")):
            raise ValueError(f"{field_name}にwildcard記法または改行を含むtraitは登録できません")
        if normalized_trait and normalized_trait not in seen_traits:
            formatted_traits.append(normalized_trait)
            seen_traits.add(normalized_trait)
    return tuple(formatted_traits)


# {
#   責務: [_outfit_traits: 既定表示する衣装profileから可視衣服traitを集約する]
#   処理: [outerwear, garment, accessoryを順に結合し, hidden innerwearは除外する]
#   引数: [outfit: 対象衣装profile]
#   戻り値: [tuple[str, ...]: 重複を除いた可視衣服trait]
#   エラー: [ValueError: traitにwildcard記法または改行を含む場合]
# }
def _outfit_traits(outfit: CharacterOutfitProfile) -> tuple[str, ...]:
    return _format_confirmed_traits(
        (*outfit.outerwear_traits, *outfit.garment_traits, *outfit.accessory_traits),
        f"outfit {outfit.outfit_id}",
    )


# {
#   責務: [build_character_wildcard_files: 確認済みCharacterProfileをwildcard file bundleへ変換する]
#   処理: [identityと確認済み衣装を分離し, default outfit参照とLoRA wrapperを生成する]
#   引数: [profile: 書き出すCharacterProfile]
#   戻り値: [dict[str, str]: root相対POSIX pathとUTF-8本文の対応]
#   エラー: [ValueError: confirmed identityが空またはwildcard本文に不正値を含む場合]
# }
def build_character_wildcard_files(profile: CharacterProfile) -> dict[str, str]:
    """Render confirmed profile data as wildcard paths and UTF-8 file contents."""
    identity_traits = _format_confirmed_traits(
        profile.confirmed_core_traits, "confirmed_core_traits"
    )
    if not identity_traits:
        raise ValueError("wildcardを書き出すには確認済みidentity traitが必要です")

    character_id = profile.character_id
    identity_path = PurePosixPath("anime_character") / character_id / "identity.txt"
    main_character_path = PurePosixPath("anime_character") / f"{character_id}.txt"
    wrapper_path = PurePosixPath("character_with_lora") / f"{character_id}.txt"
    files = {
        identity_path.as_posix(): f"{', '.join(identity_traits)}\n",
    }
    main_references = [f"__anime_character/{character_id}/identity__"]

    for outfit in profile.outfit_profiles:
        if not outfit.user_confirmed:
            continue
        traits = _outfit_traits(outfit)
        if not traits:
            continue
        outfit_path = (
            PurePosixPath("anime_character") / character_id / "outfit" / f"{outfit.outfit_id}.txt"
        )
        files[outfit_path.as_posix()] = f"{', '.join(traits)}\n"
        if outfit.outfit_id == profile.default_outfit_id:
            main_references.append(f"__anime_character/{character_id}/outfit/{outfit.outfit_id}__")

    files[main_character_path.as_posix()] = f"{' '.join(main_references)}\n"
    files[wrapper_path.as_posix()] = (
        f"__character_lora/{character_id}__ __anime_character/{character_id}__\n"
    )
    return files
