"""Task-aware caption ownership and reproducible multi-caption selection."""

from __future__ import annotations

import re
import unicodedata

from comfyui_support_tools.shared.contracts.dataset_curator import (
    CaptionPolicy,
    CaptionSet,
    CuratorConfig,
    CuratorTask,
    DatasetSampleInput,
)

_TAG_ALIASES = {
    "indoors": "indoor",
    "outdoors": "outdoor",
    "three_quarter_view": "three_quarter_view",
    "34_view": "three_quarter_view",
    "fullbody": "full_body",
    "full_body": "full_body",
    "close_up": "close_up",
    "closeup": "close_up",
    "smiling": "smile",
}
_CATEGORY_TAGS = {
    "pose": {
        "standing",
        "sitting",
        "walking",
        "running",
        "lying",
        "kneeling",
        "full_body",
        "upper_body",
    },
    "viewpoint": {
        "front_view",
        "side_view",
        "back_view",
        "profile",
        "three_quarter_view",
        "low_angle",
        "high_angle",
    },
    "expression": {"smile", "neutral_expression", "angry", "surprised", "closed_eyes"},
    "background": {
        "indoor",
        "outdoor",
        "forest",
        "city",
        "beach",
        "mountain",
        "studio",
        "plain_background",
    },
    "clothing": {
        "dress",
        "coat",
        "uniform",
        "armor",
        "shirt",
        "skirt",
        "pants",
        "jacket",
        "outfit",
    },
    "lighting": {
        "backlighting",
        "soft_light",
        "dramatic_lighting",
        "sunlight",
        "night",
        "blue_hour",
    },
    "composition": {
        "portrait",
        "landscape",
        "close_up",
        "wide_shot",
        "centered",
        "simple_composition",
        "complex_composition",
    },
    "style": {
        "anime",
        "watercolor",
        "oil_painting",
        "lineart",
        "cel_shading",
        "soft_shading",
        "photorealistic",
        "illustration",
    },
    "identity": {"person", "character", "woman", "man", "girl", "boy"},
    "hair": {
        "long_hair",
        "short_hair",
        "ponytail",
        "twintails",
        "blonde_hair",
        "black_hair",
        "blue_hair",
    },
    "accessory": {"glasses", "earrings", "ribbon", "hat", "headphones", "necklace"},
}
_STYLE_TASK_VARIABLE = {
    "subject",
    "object",
    "composition",
    "pose",
    "viewpoint",
    "background",
    "lighting",
    "expression",
    "identity",
    "clothing",
}
_CHARACTER_TASK_VARIABLE = {
    "pose",
    "viewpoint",
    "background",
    "lighting",
    "expression",
    "composition",
}
_CLOTHING_TASK_VARIABLE = {
    "pose",
    "viewpoint",
    "background",
    "lighting",
    "expression",
    "identity",
    "composition",
}
_OBJECT_TASK_VARIABLE = {"pose", "viewpoint", "background", "lighting", "composition", "expression"}


# {
# 責務: [normalize_tag: normalize aliases and punctuation in one tag]
# 処理: [apply Unicode compatibility normalization, case folding and stable separators]
# 引数: [value: raw tag text]
# 戻り値: [str: normalized underscore-separated tag]
# }
def normalize_tag(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    normalized = re.sub(r"[\s-]+", "_", normalized)
    normalized = re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)
    return _TAG_ALIASES.get(normalized, normalized)


# {
# 責務: [category_for_tag: map normalized vocabulary to an attribute dimension]
# 処理: [search task-neutral attribute vocabularies and label unknown tags as content]
# 引数: [tag: normalized tag]
# 戻り値: [str: coverage category]
# }
def category_for_tag(tag: str) -> str:
    for category, vocabulary in _CATEGORY_TAGS.items():
        if tag in vocabulary:
            return category
    return "subject"


# {
# 責務: [_ownership_sets: choose concept-owned and variable attributes by task]
# 処理: [apply task policy, fixed-clothing preference, Character Registry evidence and user overrides]
# 引数: [sample: source captions and metadata, config: task ownership rules, override_absorb: manual concept tags, override_variable: manual variable tags]
# 戻り値: [tuple[tuple[str, ...], tuple[str, ...]]: concept tags and variable caption tags]
# }
def _ownership_sets(
    sample: DatasetSampleInput,
    config: CuratorConfig,
    override_absorb: tuple[str, ...],
    override_variable: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    tags = tuple(dict.fromkeys(normalize_tag(tag) for tag in sample.raw_tags if normalize_tag(tag)))
    rejected = {
        normalize_tag(tag) for tag in (sample.registry.rejected_traits if sample.registry else ())
    }
    registry_absorb = (
        sample.registry.identity + sample.registry.accepted_traits if sample.registry else ()
    )
    registry_variable = (
        sample.registry.outfit + sample.registry.variable_attributes if sample.registry else ()
    )
    absorb = {normalize_tag(tag) for tag in registry_absorb} | {
        normalize_tag(tag) for tag in override_absorb
    }
    variable = {normalize_tag(tag) for tag in registry_variable} | {
        normalize_tag(tag) for tag in override_variable
    }
    task_variable = {
        CuratorTask.CHARACTER: _CHARACTER_TASK_VARIABLE
        | ({"clothing"} if not config.fixed_clothing else set()),
        CuratorTask.CLOTHING: _CLOTHING_TASK_VARIABLE,
        CuratorTask.STYLE: _STYLE_TASK_VARIABLE,
        CuratorTask.OBJECT: _OBJECT_TASK_VARIABLE,
        CuratorTask.POSE: {
            "identity",
            "background",
            "lighting",
            "clothing",
            "expression",
            "viewpoint",
            "composition",
        },
        CuratorTask.CONCEPT: {
            "pose",
            "viewpoint",
            "background",
            "lighting",
            "clothing",
            "expression",
            "composition",
        },
    }[config.task]
    default_absorb = {tag for tag in tags if category_for_tag(tag) not in task_variable}
    if config.task == CuratorTask.CHARACTER:
        owned_categories = {"identity", "hair", "accessory"}
        if config.fixed_clothing:
            owned_categories.add("clothing")
        default_absorb |= {tag for tag in tags if category_for_tag(tag) in owned_categories}
    elif config.task == CuratorTask.CLOTHING:
        default_absorb |= {
            tag
            for tag in tags
            if category_for_tag(tag) in {"identity", "hair", "accessory", "clothing"}
        }
    else:
        default_absorb |= {tag for tag in tags if category_for_tag(tag) not in task_variable}
    if absorb & variable:
        raise ValueError("a tag cannot be manually assigned as both concept-owned and variable")
    variable_tags = (variable | (set(tags) - default_absorb)) - rejected - absorb
    absorbed = (absorb | default_absorb) - rejected - variable_tags
    return tuple(sorted(absorbed)), tuple(sorted(variable_tags))


# {
# 責務: [build_captions: create auditable caption variants and selected trainer caption]
# 処理: [normalize tags, apply task ownership/overrides, construct concept/short/long/hybrid variants and select policy]
# 引数: [sample: image captions and tags, config: task/caption policy, override_absorb: manual target labels, override_variable: manual caption labels]
# 戻り値: [CaptionSet: normalized multi-caption record]
# }
def build_captions(
    sample: DatasetSampleInput,
    config: CuratorConfig,
    override_absorb: tuple[str, ...] = (),
    override_variable: tuple[str, ...] = (),
) -> CaptionSet:
    raw = tuple(dict.fromkeys(tag.strip() for tag in sample.raw_tags if tag.strip()))
    rejected = {
        normalize_tag(tag) for tag in (sample.registry.rejected_traits if sample.registry else ())
    }
    normalized = tuple(
        tag for tag in dict.fromkeys(normalize_tag(tag) for tag in raw) if tag not in rejected
    )
    absorb, variable = _ownership_sets(sample, config, override_absorb, override_variable)
    short = sample.short_caption.strip() or ", ".join(variable)
    long = sample.long_caption.strip() or ", ".join(normalized)
    concept = ", ".join(absorb)
    options = {
        CaptionPolicy.FULL_TAGS: ", ".join(normalized),
        CaptionPolicy.VARIABLE_TAGS: ", ".join(variable),
        CaptionPolicy.SHORT: short,
        CaptionPolicy.LONG: long,
        CaptionPolicy.HYBRID: ", ".join(
            part for part in (concept, short or ", ".join(variable)) if part
        ),
    }
    return CaptionSet(
        raw,
        normalized,
        short,
        long,
        concept,
        options[config.caption_policy],
        tuple(dict.fromkeys(normalize_tag(tag) for tag in sample.negative_tags)),
        sample.confidence,
        sample.source,
        absorb,
        variable,
    )
