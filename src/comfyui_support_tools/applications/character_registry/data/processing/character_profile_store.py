from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.comfyui_support_tools.shared.contracts.character_id import is_valid_character_id
from src.comfyui_support_tools.shared.contracts.character_outfit_profile import (
    CharacterOutfitProfile,
)
from src.comfyui_support_tools.shared.contracts.character_profile import CharacterProfile
from src.comfyui_support_tools.shared.contracts.character_reference_image import (
    CharacterReferenceImage,
)
from src.comfyui_support_tools.shared.contracts.character_source_asset import (
    CharacterSourceAsset,
)

PROFILE_SCHEMA_VERSION = 1


# {
#   責務: [_require_object: JSON object fieldを型検証して返す]
#   処理: [dict以外のvalueを拒否する]
#   引数: [value: JSON value, field_name: エラー表示用field名]
#   戻り値: [dict[str, Any]: object value]
#   エラー: [ValueError: valueがobjectでない場合]
# }
def _require_object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name}はJSON objectである必要があります")
    return value


# {
#   責務: [_require_string: JSON string fieldを型検証して返す]
#   処理: [必須/任意の空値条件を検査する]
#   引数: [value: JSON value, field_name: エラー表示用field名, allow_empty: 空文字許可]
#   戻り値: [str: 検証済み文字列]
#   エラー: [ValueError: valueが不正な場合]
# }
def _require_string(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{field_name}は空でない文字列である必要があります")
    return value


# {
#   責務: [_require_string_tuple: JSON arrayを文字列tupleへ厳密変換する]
#   処理: [arrayと各要素の型/空値を検証してtupleを返す]
#   引数: [value: JSON value, field_name: エラー表示用field名]
#   戻り値: [tuple[str, ...]: 検証済み文字列]
#   エラー: [ValueError: arrayまたは要素が不正な場合]
# }
def _require_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name}はJSON arrayである必要があります")
    return tuple(_require_string(item, field_name) for item in value)


# {
#   責務: [_timestamp_data: UTC timestampをJSON表現に変換する]
#   処理: [UTC offsetを維持し, Z suffixのISO 8601文字列にする]
#   引数: [value: UTC datetime]
#   戻り値: [str: ISO 8601 UTC timestamp]
# }
def _timestamp_data(value: datetime | None) -> str:
    if not isinstance(value, datetime):
        raise ValueError("profile timestampがdatetimeではありません")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


# {
#   責務: [_parse_timestamp: JSON timestamp文字列をdatetimeへ変換する]
#   処理: [ISO 8601文字列をparseし, UTC以外やnaive値を拒否する]
#   引数: [value: JSON value, field_name: エラー表示用field名]
#   戻り値: [datetime: UTC datetime]
#   エラー: [ValueError: timestampが不正な場合]
# }
def _parse_timestamp(value: Any, field_name: str) -> datetime:
    timestamp = _require_string(value, field_name)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name}がISO 8601 timestampではありません") from error
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name}はUTC timestampである必要があります")
    return parsed


# {
#   責務: [_source_asset_data: source asset contractをJSON objectへ変換する]
#   処理: [provenance情報を明示的なJSON fieldへ写す]
#   引数: [asset: source asset]
#   戻り値: [dict[str, Any]: source asset data]
# }
def _source_asset_data(asset: CharacterSourceAsset) -> dict[str, Any]:
    return {
        "caption_file": asset.caption_file,
        "image_file": asset.image_file,
        "tags": list(asset.tags),
        "outfit_id": asset.outfit_id,
        "source_url": asset.source_url,
        "source_work_id": asset.source_work_id,
        "license_status": asset.license_status,
        "training_permission": asset.training_permission,
        "source_metadata": dict(asset.source_metadata),
    }


# {
#   責務: [_source_asset_from_data: JSON objectをsource asset contractへ変換する]
#   処理: [provenance fieldの型を検証し, immutable contractを生成する]
#   引数: [value: JSON value]
#   戻り値: [CharacterSourceAsset: provenance source]
#   エラー: [ValueError: fieldが不正な場合]
# }
def _source_asset_from_data(value: Any) -> CharacterSourceAsset:
    data = _require_object(value, "provenance asset")
    image_file = data.get("image_file")
    outfit_id = data.get("outfit_id")
    if image_file is not None:
        image_file = _require_string(image_file, "image_file")
    if outfit_id is not None:
        outfit_id = _require_string(outfit_id, "outfit_id")
    source_metadata = _require_object(data.get("source_metadata", {}), "source_metadata")
    if any(
        not isinstance(metadata_value, (bool, str)) and metadata_value is not None
        for metadata_value in source_metadata.values()
    ):
        raise ValueError("source_metadata valueはstr/bool/nullで指定してください")
    return CharacterSourceAsset(
        caption_file=_require_string(data.get("caption_file"), "caption_file"),
        image_file=image_file,
        tags=_require_string_tuple(data.get("tags"), "tags"),
        outfit_id=outfit_id,
        source_url=_require_string(data.get("source_url"), "source_url", allow_empty=True),
        source_work_id=_require_string(
            data.get("source_work_id"), "source_work_id", allow_empty=True
        ),
        license_status=_require_string(data.get("license_status"), "license_status"),
        training_permission=_require_string(data.get("training_permission"), "training_permission"),
        source_metadata=tuple(source_metadata.items()),
    )


# {
#   責務: [_outfit_data: outfit profileをJSON objectへ変換する]
#   処理: [tupleをarrayへ変換し, outfit metadataを保持する]
#   引数: [outfit: outfit profile]
#   戻り値: [dict[str, Any]: outfit profile data]
# }
def _outfit_data(outfit: CharacterOutfitProfile) -> dict[str, Any]:
    return {
        "outfit_id": outfit.outfit_id,
        "name": outfit.name,
        "aliases": list(outfit.aliases),
        "outerwear_traits": list(outfit.outerwear_traits),
        "garment_traits": list(outfit.garment_traits),
        "accessory_traits": list(outfit.accessory_traits),
        "innerwear_traits": list(outfit.innerwear_traits),
        "visibility_rules": list(outfit.visibility_rules),
        "source_image_ids": list(outfit.source_image_ids),
        "confidence": outfit.confidence,
        "user_confirmed": outfit.user_confirmed,
    }


# {
#   責務: [_outfit_from_data: JSON objectをoutfit profile contractへ変換する]
#   処理: [各tuple, confidence, confirmation fieldを検証してcontractを生成する]
#   引数: [value: JSON value]
#   戻り値: [CharacterOutfitProfile: outfit profile]
#   エラー: [ValueError: fieldが不正な場合]
# }
def _outfit_from_data(value: Any) -> CharacterOutfitProfile:
    data = _require_object(value, "outfit profile")
    confidence = data.get("confidence")
    confirmed = data.get("user_confirmed")
    if confidence is not None and (
        isinstance(confidence, bool) or not isinstance(confidence, (int, float))
    ):
        raise ValueError("confidenceは数値またはnullである必要があります")
    if not isinstance(confirmed, bool):
        raise ValueError("user_confirmedはbooleanである必要があります")
    return CharacterOutfitProfile(
        outfit_id=_require_string(data.get("outfit_id"), "outfit_id"),
        name=_require_string(data.get("name"), "outfit name"),
        aliases=_require_string_tuple(data.get("aliases"), "aliases"),
        outerwear_traits=_require_string_tuple(data.get("outerwear_traits"), "outerwear_traits"),
        garment_traits=_require_string_tuple(data.get("garment_traits"), "garment_traits"),
        accessory_traits=_require_string_tuple(data.get("accessory_traits"), "accessory_traits"),
        innerwear_traits=_require_string_tuple(data.get("innerwear_traits"), "innerwear_traits"),
        visibility_rules=_require_string_tuple(data.get("visibility_rules"), "visibility_rules"),
        source_image_ids=_require_string_tuple(data.get("source_image_ids"), "source_image_ids"),
        confidence=confidence,
        user_confirmed=confirmed,
    )


# {
#   責務: [_reference_image_data: CharacterReferenceImageをJSON objectへ変換する]
#   処理: [stable ID,元path,digest,衣装割当,学習候補選択をJSON値へ写す]
#   引数: [image: reference image]
#   戻り値: [dict[str, str]: serialized reference]
# }
def _reference_image_data(image: CharacterReferenceImage) -> dict[str, str | bool | None]:
    return {
        "image_id": image.image_id,
        "source_path": image.source_path,
        "content_sha256": image.content_sha256,
        "outfit_assignment": image.outfit_assignment,
        "outfit_id": image.outfit_id,
        "selected_for_training": image.selected_for_training,
    }


# {
#   責務: [_reference_image_from_data: JSON objectをreference image contractへ変換する]
#   処理: [旧JSONの未設定値を補い, 画像参照, 衣装割当, 学習候補選択を検証して復元する]
#   引数: [value: JSON value]
#   戻り値: [CharacterReferenceImage: 参照画像metadata]
#   エラー: [ValueError: fieldが不正な場合]
# }
def _reference_image_from_data(value: Any) -> CharacterReferenceImage:
    data = _require_object(value, "reference image")
    outfit_id = data.get("outfit_id")
    if outfit_id is not None:
        outfit_id = _require_string(outfit_id, "outfit_id")
    selected_for_training = data.get("selected_for_training", False)
    if not isinstance(selected_for_training, bool):
        raise ValueError("selected_for_trainingはJSON booleanである必要があります")
    return CharacterReferenceImage(
        image_id=_require_string(data.get("image_id"), "image_id"),
        source_path=_require_string(data.get("source_path"), "source_path"),
        content_sha256=_require_string(data.get("content_sha256"), "content_sha256"),
        outfit_assignment=_require_string(
            data.get("outfit_assignment", "unknown"), "outfit_assignment"
        ),
        outfit_id=outfit_id,
        selected_for_training=selected_for_training,
    )


# {
#   責務: [_profile_data: CharacterProfileをversion付きJSON objectへ変換する]
#   処理: [tuple, nested contracts, UTC timestampをJSON互換値へ写す]
#   引数: [profile: profile contract]
#   戻り値: [dict[str, Any]: serialized profile]
# }
def _profile_data(profile: CharacterProfile) -> dict[str, Any]:
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "character_id": profile.character_id,
        "display_name": profile.display_name,
        "aliases": list(profile.aliases),
        "core_traits": list(profile.core_traits),
        "confirmed_core_traits": list(profile.confirmed_core_traits),
        "rejected_traits": list(profile.rejected_traits),
        "default_outfit_id": profile.default_outfit_id,
        "outfit_profiles": [_outfit_data(outfit) for outfit in profile.outfit_profiles],
        "reference_image_ids": list(profile.reference_image_ids),
        "reference_images": [_reference_image_data(image) for image in profile.reference_images],
        "provenance": [_source_asset_data(asset) for asset in profile.provenance],
        "created_at": _timestamp_data(profile.created_at),
        "updated_at": _timestamp_data(profile.updated_at),
    }


# {
#   責務: [_profile_from_data: JSON objectをCharacterProfile contractへ変換する]
#   処理: [schema versionと全nested fieldを検証し, profile contractを復元する]
#   引数: [value: JSON value]
#   戻り値: [CharacterProfile: immutable profile]
#   エラー: [ValueError: versionまたはfieldが不正な場合]
# }
def _profile_from_data(value: Any) -> CharacterProfile:
    data = _require_object(value, "character profile")
    version = data.get("schema_version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != PROFILE_SCHEMA_VERSION
    ):
        raise ValueError("未対応のCharacterProfile schema_versionです")
    outfits = data.get("outfit_profiles")
    provenance = data.get("provenance")
    reference_images = data.get("reference_images", [])
    if (
        not isinstance(outfits, list)
        or not isinstance(provenance, list)
        or not isinstance(reference_images, list)
    ):
        raise ValueError(
            "outfit_profiles, reference_images, provenanceはJSON arrayである必要があります"
        )
    default_outfit_id = data.get("default_outfit_id")
    if default_outfit_id is not None:
        default_outfit_id = _require_string(default_outfit_id, "default_outfit_id")
    return CharacterProfile(
        character_id=_require_string(data.get("character_id"), "character_id"),
        display_name=_require_string(data.get("display_name"), "display_name"),
        aliases=_require_string_tuple(data.get("aliases"), "aliases"),
        core_traits=_require_string_tuple(data.get("core_traits"), "core_traits"),
        confirmed_core_traits=_require_string_tuple(
            data.get("confirmed_core_traits"), "confirmed_core_traits"
        ),
        rejected_traits=_require_string_tuple(data.get("rejected_traits"), "rejected_traits"),
        default_outfit_id=default_outfit_id,
        outfit_profiles=tuple(_outfit_from_data(outfit) for outfit in outfits),
        reference_image_ids=_require_string_tuple(
            data.get("reference_image_ids"), "reference_image_ids"
        ),
        reference_images=tuple(_reference_image_from_data(image) for image in reference_images),
        provenance=tuple(_source_asset_from_data(asset) for asset in provenance),
        created_at=_parse_timestamp(data.get("created_at"), "created_at"),
        updated_at=_parse_timestamp(data.get("updated_at"), "updated_at"),
    )


# {
#   責務: [CharacterProfileStore: explicit root配下でCharacterProfileをversioned JSONとして保存/読込する]
#   フィールド: [_directory: 呼び出し側が指定したprofile storage root]
#   処理: [character ID filenameの検証, atomic save, schema-aware loadを行う]
# }
class CharacterProfileStore:
    # {
    #   責務: [__init__: 呼び出し側が指定した保存rootを保持する]
    #   処理: [root pathをPathへ変換してinstance stateへ設定する]
    #   引数: [self: store instance, directory: app config等で解決した保存root]
    #   戻り値: []
    # }
    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    # {
    #   責務: [save: profileを同一directory内のtemporary file経由でatomic保存する]
    #   処理: [明示rootを作り, JSONをfsyncしてos.replaceする]
    #   引数: [profile: immutable character profile]
    #   戻り値: [Path: 保存先file]
    #   エラー: [OSError: storage I/O失敗, ValueError: ID/schema不正]
    # }
    def save(self, profile: CharacterProfile) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        root = self._directory.resolve(strict=True)
        target = self._path_for(profile.character_id)
        self._ensure_inside_root(root, target)
        if target.is_symlink():
            raise ValueError("profile fileのsymlinkへの保存は拒否しました")
        payload = json.dumps(_profile_data(profile), ensure_ascii=False, allow_nan=False, indent=2)
        handle, temporary_name = tempfile.mkstemp(
            prefix=f".{profile.character_id}.", suffix=".tmp", dir=root
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, target)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
        return target

    # {
    #   責務: [load: character IDに対応するprofile JSONを検証して復元する]
    #   処理: [root containmentとsymlinkを確認し, versioned JSONをparseする]
    #   引数: [character_id: stable profile ID]
    #   戻り値: [CharacterProfile: immutable profile]
    #   エラー: [OSError: file read失敗, ValueError: ID/JSON/schema不正]
    # }
    def load(self, character_id: str) -> CharacterProfile:
        root = self._directory.resolve(strict=True)
        target = self._path_for(character_id)
        self._ensure_inside_root(root, target)
        if target.is_symlink():
            raise ValueError("profile file symlinkの読込は拒否しました")
        try:
            with target.open("r", encoding="utf-8") as stream:
                value = json.load(stream)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(f"CharacterProfile JSONが不正です: {error}") from error
        profile = _profile_from_data(value)
        if profile.character_id != character_id:
            raise ValueError("保存先とprofile内のcharacter_idが一致しません")
        return profile

    # {
    #   責務: [_path_for: stable character IDから保存先pathを作る]
    #   処理: [共通ID形式を検証し, root直下のJSON filenameを返す]
    #   引数: [character_id: stable profile ID]
    #   戻り値: [Path: profile JSON path]
    #   エラー: [ValueError: character IDが不正な場合]
    # }
    def _path_for(self, character_id: str) -> Path:
        if not is_valid_character_id(character_id):
            raise ValueError("character_idは小文字英数字と-_の1〜64文字で指定してください")
        return self._directory / f"{character_id}.json"

    # {
    #   責務: [_ensure_inside_root: profile pathが指定rootの直下か確認する]
    #   処理: [resolved parentとresolved rootが一致しないpathを拒否する]
    #   引数: [root: 明示storage root, candidate: 保存/読込候補path]
    #   戻り値: []
    #   エラー: [ValueError: pathがroot外を指す場合]
    # }
    @staticmethod
    def _ensure_inside_root(root: Path, candidate: Path) -> None:
        try:
            candidate.resolve(strict=False).relative_to(root)
        except (OSError, ValueError) as error:
            raise ValueError("CharacterProfile pathは明示storage root内に限定します") from error
