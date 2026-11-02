"""Contracts for model-specific anime generation behavior."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType


# {
#   責務: [AnimeModelFamily: distinguish anime-specific SDXL ecosystems]
#   フィールド: [ANIMAGINE, ILLUSTRIOUS, NOOBAI]
#   処理: [represent prompt and LoRA ecosystems independently from the base SDXL architecture]
# }
class AnimeModelFamily(str, Enum):
    GENERAL_SDXL = "general_sdxl"
    ANIMAGINE = "animagine"
    ILLUSTRIOUS = "illustrious"
    NOOBAI = "noobai"


# {
#   責務: [AnimeIntent: represent a target use case for anime generation]
#   フィールド: [GENERAL, CHARACTER, BACKGROUND, MANGA]
#   処理: [select use-case metadata without implying a measured quality ranking]
# }
class AnimeIntent(str, Enum):
    GENERAL = "general"
    CHARACTER = "character"
    BACKGROUND = "background"
    MANGA = "manga"


# {
#   責務: [AnimeContentMode: identify an optional generation content profile]
#   フィールド: [UNSPECIFIED, SFW, NSFW]
#   処理: [apply model-native rating tags only when the caller explicitly selected a mode]
# }
class AnimeContentMode(str, Enum):
    UNSPECIFIED = "unspecified"
    SFW = "sfw"
    NSFW = "nsfw"


# {
#   責務: [AnimePromptPolicy: store one model family's prompt transformation rules]
#   フィールド: [quality tags, intent tags, content tags, negative terms, ordering]
#   処理: [separate model vocabulary from the generic prompt transformation algorithm]
# }
@dataclass(frozen=True)
class AnimePromptPolicy:
    quality_tags: tuple[str, ...]
    intent_tags: Mapping[AnimeIntent, tuple[str, ...]] = field(default_factory=dict)
    content_tags: Mapping[AnimeContentMode, tuple[str, ...]] = field(default_factory=dict)
    negative_tags: tuple[str, ...] = ()
    quality_position: str = "prefix"

    # {
    #   責務: [__post_init__: validate and freeze one prompt policy]
    #   処理: [require known policy positions, nonempty tag strings, and immutable intent mappings]
    #   引数: [self: prompt policy]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if self.quality_position not in {"prefix", "suffix"}:
            raise ValueError("quality_position must be prefix or suffix")
        _validate_tags(self.quality_tags, "quality_tags")
        _validate_tags(self.negative_tags, "negative_tags")
        for intent, tags in self.intent_tags.items():
            if not isinstance(intent, AnimeIntent):
                raise ValueError("intent_tags keys must be AnimeIntent values")
            _validate_tags(tags, "intent_tags")
        for mode, tags in self.content_tags.items():
            if not isinstance(mode, AnimeContentMode) or mode is AnimeContentMode.UNSPECIFIED:
                raise ValueError("content_tags keys must be SFW or NSFW")
            _validate_tags(tags, "content_tags")
        object.__setattr__(self, "intent_tags", MappingProxyType(dict(self.intent_tags)))
        object.__setattr__(self, "content_tags", MappingProxyType(dict(self.content_tags)))


# {
#   責務: [AnimeModelProfile: describe a replaceable model ecosystem profile]
#   フィールド: [family, aliases, lineage, resolution, prompt policy, LoRA compatibility, license evidence]
#   処理: [allow an additional model family to register data without editing routing algorithms]
# }
@dataclass(frozen=True)
class AnimeModelProfile:
    profile_id: str
    family: str
    aliases: tuple[str, ...]
    lineage: str
    native_resolution: int
    prompt_policy: AnimePromptPolicy
    lora_compatible_families: frozenset[str]
    license_reference: str = ""
    training_base_suitability: str = "unknown"
    recommended_intents: tuple[AnimeIntent, ...] = ()

    # {
    #   責務: [__post_init__: validate a declarative model-family profile]
    #   処理: [bound aliases and capability metadata while avoiding inferred license claims]
    #   引数: [self: immutable model profile]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if (
            not self.profile_id.strip()
            or not isinstance(self.family, str)
            or not self.family.strip()
        ):
            raise ValueError("profile_id and family are required")
        if not self.aliases or any(not alias.strip() for alias in self.aliases):
            raise ValueError("model profile aliases must be nonempty")
        if (
            not isinstance(self.native_resolution, int)
            or isinstance(self.native_resolution, bool)
            or self.native_resolution < 64
        ):
            raise ValueError("native_resolution must be a positive usable integer")
        if not isinstance(self.prompt_policy, AnimePromptPolicy):
            raise ValueError("prompt_policy must be an AnimePromptPolicy")
        if self.family not in self.lora_compatible_families:
            raise ValueError("a model profile must include its own family in LoRA compatibility")
        if any(
            not isinstance(family, str) or not family.strip()
            for family in self.lora_compatible_families
        ):
            raise ValueError("lora_compatible_families must contain family IDs")
        if any(not isinstance(intent, AnimeIntent) for intent in self.recommended_intents):
            raise ValueError("recommended_intents must contain AnimeIntent values")
        if self.training_base_suitability not in {"unknown", "suitable", "not_recommended"}:
            raise ValueError("training_base_suitability must be a declared suitability value")


# {
#   責務: [AnimeLoraRequirement: state one LoRA's evidenced ecosystem compatibility]
#   フィールド: [name, compatible families, required flag]
#   処理: [prevent a router from selecting a known-incompatible model for a required adapter]
# }
@dataclass(frozen=True)
class AnimeLoraRequirement:
    name: str
    compatible_families: frozenset[str]
    required: bool = True

    # {
    #   責務: [__post_init__: validate LoRA family evidence]
    #   処理: [require a name and known-compatible anime family declarations]
    #   引数: [self: required LoRA metadata]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if not self.name.strip() or not self.compatible_families:
            raise ValueError("LoRA name and at least one compatible family are required")
        if any(
            not isinstance(family, str) or not family.strip() for family in self.compatible_families
        ):
            raise ValueError("compatible_families must contain family IDs")
        if not isinstance(self.required, bool):
            raise ValueError("required must be a boolean")


# {
#   責務: [AnimeRouteRequest: define explicit model and LoRA routing constraints]
#   フィールド: [available models, intent, explicit selection, LoRA requirements]
#   処理: [keep user-selected model priority ahead of soft use-case preferences]
# }
@dataclass(frozen=True)
class AnimeRouteRequest:
    available_models: tuple[str, ...]
    intent: AnimeIntent = AnimeIntent.GENERAL
    explicit_model: str | None = None
    required_loras: tuple[AnimeLoraRequirement, ...] = ()

    # {
    #   責務: [__post_init__: validate a bounded routing request]
    #   処理: [require model names, a typed intent, and typed LoRA requirements]
    #   引数: [self: route request]
    #   戻り値: []
    # }
    def __post_init__(self) -> None:
        if any(not isinstance(name, str) or not name.strip() for name in self.available_models):
            raise ValueError("available_models must contain nonempty model names")
        if not isinstance(self.intent, AnimeIntent):
            raise ValueError("intent must be an AnimeIntent")
        if self.explicit_model is not None and self.explicit_model not in self.available_models:
            raise ValueError("explicit_model must be one of the available models")
        if any(not isinstance(item, AnimeLoraRequirement) for item in self.required_loras):
            raise ValueError("required_loras must contain AnimeLoraRequirement values")


# {
#   責務: [AnimeRouteResult: explain one deterministic model routing outcome]
#   フィールド: [selected model, profile, ordered alternatives, reason]
#   処理: [surface compatible candidates and transparent capability-based reasoning]
# }
@dataclass(frozen=True)
class AnimeRouteResult:
    selected_model: str
    profile: AnimeModelProfile
    ranked_models: tuple[str, ...]
    reason: str


# {
#   責務: [AnimeRoutingError: report that no model meets explicit routing constraints]
#   フィールド: [ValueError details]
#   処理: [stop generation rather than silently selecting an incompatible family]
# }
class AnimeRoutingError(ValueError):
    """Raised when no registered model satisfies the explicit request constraints."""


# {
#   責務: [_validate_tags: require prompt policy tag tuples to contain nonempty strings]
#   処理: [reject malformed registry descriptors before they are applied]
#   引数: [tags: tag sequence, field_name: validation context]
#   戻り値: []
# }
def _validate_tags(tags: tuple[str, ...], field_name: str) -> None:
    if not isinstance(tags, tuple) or any(
        not isinstance(tag, str) or not tag.strip() for tag in tags
    ):
        raise ValueError(f"{field_name} must contain nonempty text tags")
