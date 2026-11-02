"""Crash-safe local JSON storage for versioned character profiles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path

from comfyui_support_tools.shared.contracts.character_registry import (
    CharacterImage,
    CharacterProfile,
    CharacterTrait,
    OutfitProfile,
    validate_character_profile,
)

CHARACTER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


# {
#   責務: [save_character_profile: validate後のprofileをatomic JSON replaceで保存する]
#   処理: [1: stable IDと既存pathを検証する 2: expected hashで競合を検出する 3: validate済みJSONをatomic publishする]
#   引数: [root: profile store root, profile: character asset, expected_hash: optimistic update token]
#   戻り値: [content sha256: 次回更新用token]
# }
def save_character_profile(
    root: Path, profile: CharacterProfile, *, expected_hash: str | None = None
) -> str:
    validate_character_profile(profile)
    if not CHARACTER_ID_PATTERN.fullmatch(profile.character_id):
        raise ValueError("character_id must be a safe stable identifier")
    store_root = Path(root).expanduser().resolve()
    store_root.mkdir(parents=True, exist_ok=True)
    target = store_root / f"{profile.character_id}.json"
    if target.is_symlink():
        raise ValueError("character profile cannot be a symlink")
    current_hash = _file_hash(target) if target.exists() else None
    if current_hash != expected_hash:
        raise FileExistsError("character profile changed or already exists; reload before saving")
    payload = json.dumps(asdict(profile), ensure_ascii=False, sort_keys=True, indent=2).encode(
        "utf-8"
    )
    _atomic_publish(target, payload, expected_hash=expected_hash)
    return hashlib.sha256(payload).hexdigest()


# {
#   責務: [load_character_profile: saved profileをtyped contractへ復元してvalidationする]
#   処理: [1: stable ID pathを解決する 2: JSON nested arraysをtuple/DTOへ変換する 3: contractを検証する]
#   引数: [root: profile store root, character_id: stable identifier]
#   戻り値: [CharacterProfile]
# }
def load_character_profile(root: Path, character_id: str) -> CharacterProfile:
    if not CHARACTER_ID_PATTERN.fullmatch(character_id):
        raise ValueError("character_id must be a safe stable identifier")
    target = Path(root).expanduser().resolve() / f"{character_id}.json"
    if target.is_symlink() or not target.is_file():
        raise FileNotFoundError(target)
    raw = json.loads(target.read_text(encoding="utf-8"))
    profile = _deserialize_profile(raw)
    validate_character_profile(profile)
    return profile


# {
#   責務: [list_character_ids: profile store内のvalidなID形式のjson filenameを安定順に返す]
#   処理: [1: store rootを検査する 2: safe IDに合うJSON filenameをsortして返す]
#   引数: [root: profile store root]
#   戻り値: [character IDs]
# }
def list_character_ids(root: Path) -> tuple[str, ...]:
    store_root = Path(root).expanduser().resolve()
    if not store_root.exists():
        return ()
    if not store_root.is_dir():
        raise NotADirectoryError(store_root)
    return tuple(
        sorted(
            path.stem
            for path in store_root.glob("*.json")
            if CHARACTER_ID_PATTERN.fullmatch(path.stem) and not path.is_symlink()
        )
    )


# {
#   責務: [character_profile_version: selected profile bytesをhashしoptimistic update tokenを返す]
#   処理: [1: safe IDを確認する 2: non-symlink file hashを返す]
#   引数: [root: profile store root, character_id: stable identifier]
#   戻り値: [sha256 update token]
# }
def character_profile_version(root: Path, character_id: str) -> str:
    if not CHARACTER_ID_PATTERN.fullmatch(character_id):
        raise ValueError("character_id must be a safe stable identifier")
    target = Path(root).expanduser().resolve() / f"{character_id}.json"
    if target.is_symlink() or not target.is_file():
        raise FileNotFoundError(target)
    return _file_hash(target)


# {
#   責務: [resolve_character_reference: stable ID/name/aliasを一意なCharacterProfileへ解決する]
#   処理: [1: queryを正規化する 2: valid profilesからcase-insensitive matchを集める 3: ambiguityを拒否する]
#   引数: [root: profile store root, query: character ID/display name/alias]
#   戻り値: [unique CharacterProfile]
# }
def resolve_character_reference(root: Path, query: str) -> CharacterProfile:
    normalized = query.strip().casefold()
    if not normalized:
        raise ValueError("character reference must be non-empty")
    matches = []
    for character_id in list_character_ids(root):
        profile = load_character_profile(root, character_id)
        references = (profile.character_id, profile.display_name, profile.trigger_name or "")
        references += profile.aliases
        if normalized in {value.casefold() for value in references if value}:
            matches.append(profile)
    if not matches:
        raise FileNotFoundError(f"no character matches {query!r}")
    if len(matches) > 1:
        raise ValueError(f"character reference is ambiguous: {query!r}")
    return matches[0]


# {
#   責務: [_deserialize_profile: JSON mappingをnested immutable profile DTOへ変換する]
#   処理: [1: trait/outfit/image nested collectionsを復元する 2: CharacterProfileを構築する]
#   引数: [raw: decoded JSON object]
#   戻り値: [CharacterProfile]
# }
def _deserialize_profile(raw: dict[str, object]) -> CharacterProfile:
    def traits(items: object) -> tuple[CharacterTrait, ...]:
        return tuple(
            CharacterTrait(
                item["category"],
                item["value"],
                item.get("confidence", 1.0),
                item.get("source", "user"),
                tuple(item.get("visibility_conditions", ())),
            )
            for item in items
        )

    outfits = tuple(
        OutfitProfile(
            item["outfit_id"],
            item["name"],
            tuple(item.get("aliases", ())),
            traits(item.get("traits", ())),
            traits(item.get("hidden_traits", ())),
            tuple(item.get("source_image_ids", ())),
            item.get("is_default", False),
            item.get("confidence", 1.0),
            item.get("user_confirmed", False),
        )
        for item in raw.get("outfit_profiles", ())
    )
    images = tuple(
        CharacterImage(
            item["image_id"],
            item["source_uri"],
            item["sha256"],
            item.get("outfit_id"),
            item.get("managed_original_uri"),
            item.get("managed_webp_uri"),
            item.get("width"),
            item.get("height"),
            item.get("quality_score"),
            item.get("identity_score"),
            item.get("selected_for_training", True),
            tuple(tuple(entry) for entry in item.get("provenance", ())),
        )
        for item in raw.get("image_refs", ())
    )
    return CharacterProfile(
        raw["character_id"],
        raw["display_name"],
        tuple(raw.get("aliases", ())),
        raw.get("trigger_name"),
        traits(raw.get("core_traits", ())),
        traits(raw.get("rejected_traits", ())),
        outfits,
        raw.get("default_outfit_id"),
        images,
        raw.get("prompt_policy", "balanced"),
        tuple(tuple(item) for item in raw.get("dataset_stats", ())),
        tuple(tuple(item) for item in raw.get("personalization_artifacts", ())),
        tuple(tuple(item) for item in raw.get("provenance", ())),
        raw.get("created_at", ""),
        raw.get("updated_at", ""),
    )


# {
#   責務: [_file_hash: current profile versionをhashしてoptimistic lockに使う]
#   処理: [1: existing file bytesを読む 2: SHA-256 digestを返す]
#   引数: [path: profile json]
#   戻り値: [sha256: content digest]
# }
def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# {
#   責務: [_atomic_publish: same-directory temporary fileをflush後にatomic replaceする]
#   処理: [1: exclusive temp fileを作る 2: fsyncする 3: os.replaceする 4: 失敗時temporaryを消す]
#   引数: [target: destination JSON, payload: serialized bytes]
#   戻り値: []
# }
def _atomic_publish(target: Path, payload: bytes, *, expected_hash: str | None) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        current_hash = _file_hash(target) if target.exists() else None
        if current_hash != expected_hash:
            raise FileExistsError("character profile changed during save")
        os.replace(temporary_name, target)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
