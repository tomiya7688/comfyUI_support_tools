"""Serializable contracts for registered characters, outfits, and images."""

from __future__ import annotations

from dataclasses import dataclass, field


# {
#   責務: [validate_character_profile: persisted CharacterProfileのcross-referenceとmeasurementを検証する]
#   処理: [1: IDs/default outfit/image referencesを確認する 2: trait/image evidenceの範囲を検証する]
#   引数: [profile: candidate character asset]
#   戻り値: []
# }
def validate_character_profile(profile: CharacterProfile) -> None:
    if not profile.character_id.strip() or not profile.display_name.strip():
        raise ValueError("character_id and display_name must be non-empty")
    outfit_ids = [item.outfit_id for item in profile.outfit_profiles]
    if len(outfit_ids) != len(set(outfit_ids)) or any(not item for item in outfit_ids):
        raise ValueError("outfit IDs must be non-empty and unique")
    if profile.default_outfit_id and profile.default_outfit_id not in outfit_ids:
        raise ValueError("default_outfit_id must reference a registered outfit")
    marked_defaults = [item.outfit_id for item in profile.outfit_profiles if item.is_default]
    if len(marked_defaults) > 1 or (
        marked_defaults and marked_defaults[0] != profile.default_outfit_id
    ):
        raise ValueError("outfit default marker must agree with default_outfit_id")
    image_ids = [item.image_id for item in profile.image_refs]
    if len(image_ids) != len(set(image_ids)) or any(not item for item in image_ids):
        raise ValueError("image IDs must be non-empty and unique")
    if any(item.outfit_id and item.outfit_id not in outfit_ids for item in profile.image_refs):
        raise ValueError("image outfit_id must reference a registered outfit")
    if any(
        not item.source_uri
        or not item.sha256
        or (item.width is not None and item.width <= 0)
        or (item.height is not None and item.height <= 0)
        or any(
            score is not None and not 0 <= score <= 1
            for score in (item.quality_score, item.identity_score)
        )
        for item in profile.image_refs
    ):
        raise ValueError("image references must contain source/hash and valid measurements")
    if profile.prompt_policy not in {"balanced", "compact", "verbatim"}:
        raise ValueError("unsupported character prompt policy")
    traits = list(profile.core_traits + profile.rejected_traits)
    for outfit in profile.outfit_profiles:
        traits.extend(outfit.traits + outfit.hidden_traits)
    if any(
        not item.category.strip() or not item.value.strip() or not 0 <= item.confidence <= 1
        for item in traits
    ):
        raise ValueError("traits must have non-empty values and confidence within 0..1")


# {
#   責務: [CharacterTrait: identity/outfit/contextへ分類されたtraitを保持する]
#   フィールド: [category、value、confidence、provenance、visibility condition]
# }
@dataclass(frozen=True)
class CharacterTrait:
    category: str
    value: str
    confidence: float = 1.0
    source: str = "user"
    visibility_conditions: tuple[str, ...] = ()


# {
#   責務: [OutfitProfile: character identityと独立した衣装trait setを保持する]
#   フィールド: [stable id、name、aliases、garment/accessory/innerwear traits、source images]
# }
@dataclass(frozen=True)
class OutfitProfile:
    outfit_id: str
    name: str
    aliases: tuple[str, ...] = ()
    traits: tuple[CharacterTrait, ...] = ()
    hidden_traits: tuple[CharacterTrait, ...] = ()
    source_image_ids: tuple[str, ...] = ()
    is_default: bool = False
    confidence: float = 1.0
    user_confirmed: bool = False


# {
#   責務: [CharacterImage: image source/reference/hash/training選択状態を保持する]
#   フィールド: [stable id、source uri、hash/geometry、managed WebP uri、quality]
# }
@dataclass(frozen=True)
class CharacterImage:
    image_id: str
    source_uri: str
    sha256: str
    outfit_id: str | None = None
    managed_original_uri: str | None = None
    managed_webp_uri: str | None = None
    width: int | None = None
    height: int | None = None
    quality_score: float | None = None
    identity_score: float | None = None
    selected_for_training: bool = True
    provenance: tuple[tuple[str, str], ...] = ()


# {
#   責務: [CharacterProfile: nameと切り離されたstable character assetを保持する]
#   フィールド: [id、aliases、core traits、outfits、images、policy、artifacts、provenance]
# }
@dataclass(frozen=True)
class CharacterProfile:
    character_id: str
    display_name: str
    aliases: tuple[str, ...] = ()
    trigger_name: str | None = None
    core_traits: tuple[CharacterTrait, ...] = ()
    rejected_traits: tuple[CharacterTrait, ...] = ()
    outfit_profiles: tuple[OutfitProfile, ...] = ()
    default_outfit_id: str | None = None
    image_refs: tuple[CharacterImage, ...] = ()
    prompt_policy: str = "balanced"
    dataset_stats: tuple[tuple[str, float], ...] = ()
    personalization_artifacts: tuple[tuple[str, str], ...] = ()
    provenance: tuple[tuple[str, str], ...] = ()
    created_at: str = ""
    updated_at: str = ""


# {
#   責務: [VisibilityContext: hidden traitの露出判定に使う観測を記録する]
#   フィールド: [pose、camera、material、scene signals、明示指示]
# }
@dataclass(frozen=True)
class VisibilityContext:
    pose_signals: tuple[str, ...] = ()
    camera_signals: tuple[str, ...] = ()
    material_signals: tuple[str, ...] = ()
    scene_signals: tuple[str, ...] = ()
    explicit_attribute_requests: tuple[str, ...] = ()


# {
#   責務: [VisibilityDecision: hidden traitを挿入する理由/confidence/actionを返す]
#   フィールド: [trait、likelihood、confidence、reason、inject]
# }
@dataclass(frozen=True)
class VisibilityDecision:
    attribute: str
    visible_likelihood: float
    transparency_likelihood: float
    confidence: float
    reasons: tuple[str, ...] = ()
    action: str = "omit"


# {
#   責務: [CharacterPromptResolution: resolved prompt traitsとsuppressed categoriesを返す]
#   フィールド: [character/outfit identity、included traits、hidden decisions、suppression]
# }
@dataclass(frozen=True)
class CharacterPromptResolution:
    character_id: str
    outfit_id: str | None
    traits: tuple[str, ...]
    hidden_decisions: tuple[VisibilityDecision, ...] = ()
    suppressed_categories: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


# {
#   責務: [CharacterDatasetReadiness: training用画像の有効数と品質警告を返す]
#   フィールド: [effective count、duplicate ratio、quality/diversity、strategy suggestion、warnings]
# }
@dataclass(frozen=True)
class CharacterDatasetReadiness:
    selected_image_count: int
    effective_image_count: float
    duplicate_ratio: float
    mean_quality: float | None
    outfit_count: int
    suggested_strategy: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
