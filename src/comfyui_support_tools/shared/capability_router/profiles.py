"""Conservative built-in capability descriptors for documented model families."""

from __future__ import annotations

from .contracts import (
    CapabilityFeature,
    GenerationCapability,
    GenerationUseCase,
    LatencyClass,
    LicenseEvidence,
    ModelLifecycle,
    QualityClass,
)

_NATURAL_T2I = frozenset({CapabilityFeature.TXT2IMG, CapabilityFeature.NATURAL_LANGUAGE})
_PHOTO_USE_CASES = frozenset(
    {
        GenerationUseCase.GENERAL,
        GenerationUseCase.PHOTOREALISTIC,
        GenerationUseCase.FAST_DRAFT,
        GenerationUseCase.LOW_VRAM,
    }
)


# {
#   責務: [create_default_capabilities: issueで言及されたmodel familiesをcapability metadataへ登録する]
#   処理: [known factsとunknown license/resource/workflow fieldsを区別し, empirical winnerを宣言しない]
#   引数: []
#   戻り値: [tuple[GenerationCapability, ...]: registryへ投入可能なdescriptors]
#   注意: [license evidence, workflow compatibility, memory valuesはmanifest source確認が必要]
# }
# {
#   責務: [create_default_capabilities: issueで言及されたmodel familiesをcapability metadataへ登録する]
#   処理: [combine independently maintained profile groups without declaring empirical winners]
#   引数: []
#   戻り値: [tuple[GenerationCapability, ...]: registryへ投入可能なdescriptors]
#   注意: [license/resource/workflow facts require source evidence]
# }
def create_default_capabilities() -> tuple[GenerationCapability, ...]:
    return (*_flux_profiles(), *_multimodal_profiles(), *_sana_profile(), *_anime_profile())


# {
#   責務: [_flux_profiles: built-in family groupを作る]
#   処理: [return immutable capability declarations for this model family group]
#   引数: []
#   戻り値: [tuple[GenerationCapability, ...]: declared profile group]
# }
def _flux_profiles() -> tuple[GenerationCapability, ...]:
    return (
        GenerationCapability(
            profile_id="flux2_klein_4b_distilled",
            family="flux2_klein",
            aliases=("flux2 klein 4b", "flux.2 klein 4b", "flux2-klein-4b"),
            backend="comfyui",
            features=frozenset(
                {
                    *_NATURAL_T2I,
                    CapabilityFeature.IMG2IMG,
                    CapabilityFeature.REFERENCE_IMAGES,
                }
            ),
            recommended_use_cases=_PHOTO_USE_CASES,
            prompt_policy_id="natural_language_v1",
            workflow_profile_id="flux2_klein_4b",
            minimum_vram_gib=8,
            minimum_ram_gib=16,
            recommended_steps=4,
            quantized_vram_gib=(("int8", 6), ("int4", 4)),
            maximum_resolution=None,
            latency_class=LatencyClass.FAST,
            quality_class=QualityClass.DRAFT,
            license=LicenseEvidence(
                "Apache-2.0",
                True,
                "https://github.com/black-forest-labs/flux2",
                verified=False,
            ),
            lifecycle=ModelLifecycle.EXPERIMENTAL,
            evidence_reference="https://github.com/black-forest-labs/flux2",
        ),
        GenerationCapability(
            profile_id="flux2_klein_4b_base",
            family="flux2_klein",
            aliases=("flux2 klein 4b base", "flux.2 klein 4b base"),
            backend="comfyui",
            features=frozenset(
                {
                    *_NATURAL_T2I,
                    CapabilityFeature.IMG2IMG,
                    CapabilityFeature.LORA_FINETUNE,
                }
            ),
            recommended_use_cases=frozenset(
                {GenerationUseCase.GENERAL, GenerationUseCase.LORA_CENTRIC}
            ),
            prompt_policy_id="natural_language_v1",
            workflow_profile_id="flux2_klein_4b_base",
            minimum_vram_gib=12,
            minimum_ram_gib=24,
            recommended_steps=30,
            quantized_vram_gib=(),
            maximum_resolution=None,
            latency_class=LatencyClass.MEDIUM,
            quality_class=QualityClass.UNKNOWN,
            license=LicenseEvidence(
                "Apache-2.0",
                True,
                "https://github.com/black-forest-labs/flux2",
                verified=False,
            ),
            lifecycle=ModelLifecycle.EXPERIMENTAL,
            evidence_reference="https://github.com/black-forest-labs/flux2",
        ),
        GenerationCapability(
            profile_id="flux2_dev",
            family="flux2",
            aliases=("flux2 dev", "flux.2 dev"),
            backend="comfyui",
            features=_NATURAL_T2I | frozenset({CapabilityFeature.IMG2IMG}),
            recommended_use_cases=frozenset(
                {
                    GenerationUseCase.GENERAL,
                    GenerationUseCase.PHOTOREALISTIC,
                    GenerationUseCase.HIGH_QUALITY,
                }
            ),
            prompt_policy_id="natural_language_v1",
            workflow_profile_id="flux2_dev",
            minimum_vram_gib=None,
            minimum_ram_gib=None,
            recommended_steps=None,
            quantized_vram_gib=(),
            maximum_resolution=None,
            latency_class=LatencyClass.SLOW,
            quality_class=QualityClass.HIGH,
            license=LicenseEvidence(
                "BFL-Non-Commercial",
                False,
                "https://github.com/black-forest-labs/flux2",
                verified=False,
            ),
            lifecycle=ModelLifecycle.EXPERIMENTAL,
            evidence_reference="https://github.com/black-forest-labs/flux2",
        ),
    )


# {
#   責務: [_multimodal_profiles: built-in family groupを作る]
#   処理: [return immutable capability declarations for this model family group]
#   引数: []
#   戻り値: [tuple[GenerationCapability, ...]: declared profile group]
# }
def _multimodal_profiles() -> tuple[GenerationCapability, ...]:
    return (
        GenerationCapability(
            profile_id="qwen_image_2_1",
            family="qwen_image",
            aliases=("qwen image 2.1", "qwen-image-2.1"),
            backend="comfyui",
            features=frozenset(
                {
                    *_NATURAL_T2I,
                    CapabilityFeature.TYPOGRAPHY,
                    CapabilityFeature.TRANSPARENT_RGBA,
                    CapabilityFeature.REFERENCE_IMAGES,
                    CapabilityFeature.IMG2IMG,
                }
            ),
            recommended_use_cases=frozenset(
                {
                    GenerationUseCase.GENERAL,
                    GenerationUseCase.PRODUCT,
                    GenerationUseCase.OBJECT_ASSET,
                    GenerationUseCase.TYPOGRAPHY,
                    GenerationUseCase.TRANSPARENT_ASSET,
                    GenerationUseCase.HIGH_QUALITY,
                }
            ),
            prompt_policy_id="qwen_natural_language_v1",
            workflow_profile_id="qwen_image_2_1",
            minimum_vram_gib=None,
            minimum_ram_gib=None,
            recommended_steps=None,
            quantized_vram_gib=(),
            maximum_resolution=None,
            latency_class=LatencyClass.SLOW,
            quality_class=QualityClass.UNKNOWN,
            license=LicenseEvidence("unknown", None, "https://qwenlm.github.io/", verified=False),
            lifecycle=ModelLifecycle.EXPERIMENTAL,
            evidence_reference="https://qwenlm.github.io/",
        ),
        GenerationCapability(
            profile_id="hunyuan_image_3_instruct",
            family="hunyuan_image_3",
            aliases=("hunyuan image 3.0 instruct", "hunyuanimage 3 instruct"),
            backend="comfyui",
            features=frozenset(
                {
                    *_NATURAL_T2I,
                    CapabilityFeature.PROMPT_REWRITE,
                    CapabilityFeature.REFERENCE_IMAGES,
                    CapabilityFeature.IMG2IMG,
                }
            ),
            recommended_use_cases=frozenset(
                {
                    GenerationUseCase.GENERAL,
                    GenerationUseCase.PHOTOREALISTIC,
                    GenerationUseCase.CONCEPT_ART,
                    GenerationUseCase.HIGH_QUALITY,
                }
            ),
            prompt_policy_id="hunyuan_instruction_v1",
            workflow_profile_id="hunyuan_image_3_instruct",
            minimum_vram_gib=None,
            minimum_ram_gib=None,
            recommended_steps=None,
            quantized_vram_gib=(),
            maximum_resolution=None,
            latency_class=LatencyClass.SLOW,
            quality_class=QualityClass.UNKNOWN,
            license=LicenseEvidence(
                "unknown",
                None,
                "https://github.com/Tencent-Hunyuan/HunyuanImage-3.0",
                verified=False,
            ),
            lifecycle=ModelLifecycle.EXPERIMENTAL,
            local_only=False,
            evidence_reference="https://github.com/Tencent-Hunyuan/HunyuanImage-3.0",
        ),
        GenerationCapability(
            profile_id="hidream_i1_fast",
            family="hidream_i1",
            aliases=("hidream i1 fast", "hidream-i1-fast"),
            backend="comfyui",
            features=_NATURAL_T2I,
            recommended_use_cases=frozenset(
                {GenerationUseCase.GENERAL, GenerationUseCase.FAST_DRAFT}
            ),
            prompt_policy_id="natural_language_v1",
            workflow_profile_id="hidream_i1_fast",
            minimum_vram_gib=None,
            minimum_ram_gib=None,
            recommended_steps=None,
            quantized_vram_gib=(),
            maximum_resolution=None,
            latency_class=LatencyClass.FAST,
            quality_class=QualityClass.UNKNOWN,
            license=LicenseEvidence("MIT", True, "https://github.com/HiDream-ai/HiDream-I1", False),
            lifecycle=ModelLifecycle.EXPERIMENTAL,
            evidence_reference="https://github.com/HiDream-ai/HiDream-I1",
        ),
        GenerationCapability(
            profile_id="hidream_i1_dev",
            family="hidream_i1",
            aliases=("hidream i1 dev", "hidream-i1-dev"),
            backend="comfyui",
            features=_NATURAL_T2I,
            recommended_use_cases=frozenset(
                {
                    GenerationUseCase.GENERAL,
                    GenerationUseCase.PHOTOREALISTIC,
                    GenerationUseCase.HIGH_QUALITY,
                }
            ),
            prompt_policy_id="natural_language_v1",
            workflow_profile_id="hidream_i1_dev",
            minimum_vram_gib=None,
            minimum_ram_gib=None,
            recommended_steps=None,
            quantized_vram_gib=(),
            maximum_resolution=None,
            latency_class=LatencyClass.SLOW,
            quality_class=QualityClass.UNKNOWN,
            license=LicenseEvidence("MIT", True, "https://github.com/HiDream-ai/HiDream-I1", False),
            lifecycle=ModelLifecycle.EXPERIMENTAL,
            evidence_reference="https://github.com/HiDream-ai/HiDream-I1",
        ),
    )


# {
#   責務: [_sana_profile: built-in family groupを作る]
#   処理: [return immutable capability declarations for this model family group]
#   引数: []
#   戻り値: [tuple[GenerationCapability, ...]: declared profile group]
# }
def _sana_profile() -> tuple[GenerationCapability, ...]:
    return (
        GenerationCapability(
            profile_id="sana_sprint",
            family="sana",
            aliases=("sana sprint", "sana-sprint"),
            backend="comfyui",
            features=_NATURAL_T2I,
            recommended_use_cases=frozenset(
                {
                    GenerationUseCase.FAST_DRAFT,
                    GenerationUseCase.LOW_VRAM,
                    GenerationUseCase.LANDSCAPE,
                }
            ),
            prompt_policy_id="sana_natural_v1",
            workflow_profile_id="sana_sprint",
            minimum_vram_gib=8,
            minimum_ram_gib=16,
            recommended_steps=4,
            quantized_vram_gib=(("int8", 6), ("int4", 4)),
            maximum_resolution=None,
            latency_class=LatencyClass.VERY_FAST,
            quality_class=QualityClass.DRAFT,
            license=LicenseEvidence("unknown", None, "https://github.com/NVlabs/Sana", False),
            lifecycle=ModelLifecycle.EXPERIMENTAL,
            evidence_reference="https://github.com/NVlabs/Sana",
        ),
    )


# {
#   責務: [_anime_profile: built-in family groupを作る]
#   処理: [return immutable capability declarations for this model family group]
#   引数: []
#   戻り値: [tuple[GenerationCapability, ...]: declared profile group]
# }
def _anime_profile() -> tuple[GenerationCapability, ...]:
    return (
        GenerationCapability(
            profile_id="anime_sdxl_family",
            family="sdxl_anime",
            aliases=("animagine xl", "illustrious xl", "noobai xl"),
            backend="comfyui",
            features=frozenset(
                {
                    CapabilityFeature.TXT2IMG,
                    CapabilityFeature.TAG_PROMPT,
                    CapabilityFeature.ANIME,
                    CapabilityFeature.ILLUSTRATION,
                    CapabilityFeature.CHARACTER,
                    CapabilityFeature.LORA,
                    CapabilityFeature.LORA_FINETUNE,
                }
            ),
            recommended_use_cases=frozenset(
                {
                    GenerationUseCase.ANIME,
                    GenerationUseCase.ILLUSTRATION,
                    GenerationUseCase.CHARACTER,
                    GenerationUseCase.LORA_CENTRIC,
                }
            ),
            prompt_policy_id="anime_booru_tags_v1",
            workflow_profile_id="sdxl_anime",
            minimum_vram_gib=8,
            minimum_ram_gib=16,
            recommended_steps=None,
            quantized_vram_gib=(),
            maximum_resolution=None,
            latency_class=LatencyClass.MEDIUM,
            quality_class=QualityClass.UNKNOWN,
            license=LicenseEvidence("unknown", None, "https://civitai.com/", False),
            lifecycle=ModelLifecycle.SUPPORTED,
            lora_families=frozenset({"sdxl"}),
            evidence_reference="https://civitai.com/",
        ),
    )
