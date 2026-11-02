"""Built-in data profiles for documented anime checkpoint families."""

from __future__ import annotations

from .contracts import (
    AnimeContentMode,
    AnimeIntent,
    AnimeModelFamily,
    AnimeModelProfile,
    AnimePromptPolicy,
)
from .routing import AnimeModelRegistry


# {
#   責務: [create_default_anime_model_registry: register the bundled anime model descriptors]
#   処理: [declare family aliases and prompt vocabularies as data, keeping routing logic replaceable]
#   引数: []
#   戻り値: [AnimeModelRegistry: default Animagine, Illustrious and NoobAI profile registry]
# }
def create_default_anime_model_registry() -> AnimeModelRegistry:
    character_and_general = (AnimeIntent.CHARACTER, AnimeIntent.GENERAL, AnimeIntent.MANGA)
    profiles = (
        AnimeModelProfile(
            profile_id="generic_sdxl",
            family=AnimeModelFamily.GENERAL_SDXL.value,
            aliases=("sdxl", "sd xl", "stable diffusion xl"),
            lineage="General-purpose SDXL",
            native_resolution=1024,
            prompt_policy=AnimePromptPolicy(
                quality_tags=(),
                negative_tags=(),
            ),
            lora_compatible_families=frozenset({AnimeModelFamily.GENERAL_SDXL.value}),
            training_base_suitability="unknown",
        ),
        AnimeModelProfile(
            profile_id="animagine_xl",
            family=AnimeModelFamily.ANIMAGINE.value,
            aliases=("animagine", "animagine xl", "animagine xl 4"),
            lineage="SDXL anime-focused retrain",
            native_resolution=1024,
            prompt_policy=AnimePromptPolicy(
                quality_tags=("masterpiece", "best quality"),
                intent_tags={
                    AnimeIntent.CHARACTER: ("character illustration",),
                    AnimeIntent.BACKGROUND: ("anime background", "environment illustration"),
                    AnimeIntent.MANGA: ("manga illustration",),
                },
                content_tags={
                    AnimeContentMode.SFW: ("safe",),
                    AnimeContentMode.NSFW: ("nsfw",),
                },
                negative_tags=(
                    "low quality",
                    "worst quality",
                    "bad anatomy",
                    "bad hands",
                    "text",
                    "watermark",
                ),
            ),
            lora_compatible_families=frozenset({AnimeModelFamily.ANIMAGINE.value}),
            license_reference="https://huggingface.co/cagliostrolab/animagine-xl-4.0",
            training_base_suitability="unknown",
            recommended_intents=character_and_general,
        ),
        AnimeModelProfile(
            profile_id="illustrious_xl",
            family=AnimeModelFamily.ILLUSTRIOUS.value,
            aliases=("illustrious", "illustrious xl"),
            lineage="SDXL anime/illustration family",
            native_resolution=1024,
            prompt_policy=AnimePromptPolicy(
                quality_tags=("masterpiece", "best quality", "amazing quality", "very aesthetic"),
                intent_tags={
                    AnimeIntent.CHARACTER: ("anime character illustration",),
                    AnimeIntent.BACKGROUND: ("anime scenery", "detailed background"),
                    AnimeIntent.MANGA: ("manga panel",),
                },
                content_tags={
                    AnimeContentMode.SFW: ("rating: general",),
                    AnimeContentMode.NSFW: ("rating: explicit",),
                },
                negative_tags=("low quality", "bad anatomy", "bad hands", "text", "watermark"),
            ),
            lora_compatible_families=frozenset({AnimeModelFamily.ILLUSTRIOUS.value}),
            license_reference="https://huggingface.co/OnomaAIResearch/Illustrious-XL-v2.0",
            training_base_suitability="unknown",
            recommended_intents=(AnimeIntent.GENERAL, AnimeIntent.CHARACTER, AnimeIntent.MANGA),
        ),
        AnimeModelProfile(
            profile_id="noobai_xl",
            family=AnimeModelFamily.NOOBAI.value,
            aliases=("noobai", "noob ai", "noobai xl"),
            lineage="Illustrious-derived SDXL anime family",
            native_resolution=1024,
            prompt_policy=AnimePromptPolicy(
                quality_tags=("masterpiece", "best quality", "newest"),
                intent_tags={
                    AnimeIntent.CHARACTER: ("anime character",),
                    AnimeIntent.BACKGROUND: ("anime background",),
                    AnimeIntent.MANGA: ("manga style",),
                },
                content_tags={
                    AnimeContentMode.SFW: ("safe",),
                    AnimeContentMode.NSFW: ("explicit",),
                },
                negative_tags=("low quality", "bad anatomy", "bad hands", "text", "watermark"),
            ),
            lora_compatible_families=frozenset({AnimeModelFamily.NOOBAI.value}),
            license_reference="https://huggingface.co/Laxhar/noobai-XL-1.0",
            training_base_suitability="unknown",
            recommended_intents=(AnimeIntent.CHARACTER, AnimeIntent.GENERAL, AnimeIntent.MANGA),
        ),
    )
    return AnimeModelRegistry(profiles)
