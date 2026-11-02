"""Declarative architecture profiles for evolving diffusion trainers."""

from __future__ import annotations

from dataclasses import replace

from .contracts import ArchitectureProfile, AdapterMethod, Quantization, SupportLevel


_TRAINER_SUPPORT = {
    "simpletuner": SupportLevel.SUPPORTED,
    "ai_toolkit": SupportLevel.SUPPORTED,
    "sd_scripts": SupportLevel.SUPPORTED,
}
_LORA_METHODS = {AdapterMethod.LORA.value: SupportLevel.SUPPORTED}
_LYCORIS_METHODS = {
    AdapterMethod.LOCON.value: SupportLevel.EXPERIMENTAL,
    AdapterMethod.LOHA.value: SupportLevel.EXPERIMENTAL,
    AdapterMethod.LOKR.value: SupportLevel.EXPERIMENTAL,
    AdapterMethod.DORA.value: SupportLevel.EXPERIMENTAL,
    AdapterMethod.DYLORA.value: SupportLevel.EXPERIMENTAL,
}
_LOW_VRAM_FEATURES = {
    "simpletuner": (
        "gradient_checkpointing",
        "optimizer_offload",
        "cpu_offload",
        "quantized_text_encoder",
        "cached_embeddings",
        "vae_cache",
        "lower_resolution_probe",
    ),
    "ai_toolkit": (
        "gradient_checkpointing",
        "optimizer_offload",
        "cpu_offload",
        "quantized_text_encoder",
        "cached_embeddings",
        "vae_cache",
    ),
    "sd_scripts": ("gradient_checkpointing", "optimizer_offload", "cached_embeddings", "vae_cache"),
}


# {
# 責務: [architecture_profiles: enumerate model-specific training contracts]
# 処理: [retain independent flavour, latent, text, target, schedule, method, quantization and VRAM data]
# 引数: [None: profiles are project-owned immutable declarations]
# 戻り値: [dict[str, ArchitectureProfile]: supported architecture profile registry]
# }
def architecture_profiles() -> dict[str, ArchitectureProfile]:
    profiles = (
        ArchitectureProfile(
            key="sdxl",
            family="sdxl",
            flavour="base",
            text_encoder="clip_l+clip_g",
            latent_format="sdxl_vae_4ch",
            target_modules=("unet.down_blocks.*", "unet.mid_block.*", "unet.up_blocks.*"),
            training_schedule="diffusion",
            text_encoder_trainable=True,
            minimum_vram_gib=12,
            supported_trainers=dict(_TRAINER_SUPPORT),
            methods={**_LORA_METHODS, **_LYCORIS_METHODS},
            quantization={
                "simpletuner": (Quantization.NONE, Quantization.INT8, Quantization.NF4),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4, Quantization.INT8),
                "sd_scripts": (Quantization.NONE,),
            },
        ),
        ArchitectureProfile(
            key="sdxl_anime",
            family="sdxl",
            flavour="anime-illustration",
            text_encoder="clip_l+clip_g",
            latent_format="sdxl_vae_4ch",
            target_modules=("unet.down_blocks.*", "unet.mid_block.*", "unet.up_blocks.*"),
            training_schedule="diffusion",
            text_encoder_trainable=True,
            minimum_vram_gib=12,
            supported_trainers=dict(_TRAINER_SUPPORT),
            methods={**_LORA_METHODS, **_LYCORIS_METHODS},
            quantization={
                "simpletuner": (Quantization.NONE, Quantization.INT8, Quantization.NF4),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4, Quantization.INT8),
                "sd_scripts": (Quantization.NONE,),
            },
        ),
        ArchitectureProfile(
            key="flux1",
            family="flux",
            flavour="flux.1-dev",
            text_encoder="clip_l+t5_xxl",
            latent_format="flux_packed_latent",
            target_modules=("double_blocks.*.img_attn.*", "single_blocks.*.linear*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=24,
            supported_trainers=dict(_TRAINER_SUPPORT),
            methods={**_LORA_METHODS, **_LYCORIS_METHODS},
            quantization={
                "simpletuner": (Quantization.NONE, Quantization.FP8),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4, Quantization.INT8),
                "sd_scripts": (Quantization.NONE,),
            },
        ),
        ArchitectureProfile(
            key="flux2_dev",
            family="flux2",
            flavour="dev-32b",
            text_encoder="qwen3_8b",
            latent_format="flux2_latent",
            target_modules=("transformer_blocks.*.attn.*", "single_transformer_blocks.*.attn.*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=48,
            dataset_kind="image_caption",
            supported_trainers={
                "simpletuner": SupportLevel.SUPPORTED,
                "ai_toolkit": SupportLevel.SUPPORTED,
                "sd_scripts": SupportLevel.UNSUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "simpletuner": (Quantization.NONE, Quantization.FP8),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4, Quantization.INT8),
            },
        ),
        ArchitectureProfile(
            key="flux2_klein_9b",
            family="flux2",
            flavour="klein-9b",
            text_encoder="qwen3_8b",
            latent_format="flux2_klein_latent",
            target_modules=("transformer_blocks.*.attn.*", "single_transformer_blocks.*.attn.*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=24,
            supported_trainers={
                "simpletuner": SupportLevel.SUPPORTED,
                "ai_toolkit": SupportLevel.SUPPORTED,
                "sd_scripts": SupportLevel.UNSUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "simpletuner": (Quantization.NONE, Quantization.FP8),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4, Quantization.INT8),
            },
        ),
        ArchitectureProfile(
            key="flux2_klein_4b",
            family="flux2",
            flavour="klein-4b",
            text_encoder="qwen3_4b",
            latent_format="flux2_klein_latent",
            target_modules=("transformer_blocks.*.attn.*", "single_transformer_blocks.*.attn.*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=16,
            supported_trainers={
                "simpletuner": SupportLevel.SUPPORTED,
                "ai_toolkit": SupportLevel.SUPPORTED,
                "sd_scripts": SupportLevel.UNSUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "simpletuner": (Quantization.NONE, Quantization.FP8),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4, Quantization.INT8),
            },
        ),
        ArchitectureProfile(
            key="qwen_image",
            family="qwen_image",
            flavour="base-2512",
            text_encoder="qwen2.5_vl_7b",
            latent_format="qwen_image_vae",
            target_modules=("transformer_blocks.*.attn.*", "transformer_blocks.*.ff.*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=32,
            supported_trainers={
                "simpletuner": SupportLevel.SUPPORTED,
                "ai_toolkit": SupportLevel.SUPPORTED,
                "sd_scripts": SupportLevel.UNSUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "simpletuner": (Quantization.NONE,),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4, Quantization.INT8),
            },
        ),
        ArchitectureProfile(
            key="qwen_image_2_1",
            family="qwen_image",
            flavour="2.1-multistage",
            text_encoder="qwen3_8b_multimodal",
            latent_format="qwen_image_2_1_latent",
            target_modules=("transformer_blocks.*.attn.*", "assistant_lora.*"),
            training_schedule="multistage_flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=48,
            supported_trainers={
                "simpletuner": SupportLevel.EXPERIMENTAL,
                "ai_toolkit": SupportLevel.EXPERIMENTAL,
                "sd_scripts": SupportLevel.UNSUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "simpletuner": (Quantization.NONE,),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4),
            },
        ),
        ArchitectureProfile(
            key="qwen_image_edit",
            family="qwen_image",
            flavour="edit-reference-conditioned",
            text_encoder="qwen2.5_vl_7b",
            latent_format="qwen_image_edit_paired_latent",
            target_modules=("transformer_blocks.*.attn.*", "transformer_blocks.*.ff.*"),
            training_schedule="paired_flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=32,
            dataset_kind="paired_reference_edit",
            supported_trainers={
                "simpletuner": SupportLevel.EXPERIMENTAL,
                "ai_toolkit": SupportLevel.SUPPORTED,
                "sd_scripts": SupportLevel.UNSUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={"ai_toolkit": (Quantization.NONE, Quantization.NF4, Quantization.INT8)},
        ),
        ArchitectureProfile(
            key="sd3_5",
            family="sd3",
            flavour="3.5-large-medium",
            text_encoder="clip_l+clip_g+t5_xxl",
            latent_format="sd3_16ch",
            target_modules=("transformer_blocks.*.attn.*", "transformer_blocks.*.ff.*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=24,
            supported_trainers=dict(_TRAINER_SUPPORT),
            methods={**_LORA_METHODS, **_LYCORIS_METHODS},
            quantization={
                "simpletuner": (Quantization.NONE, Quantization.FP8),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4),
                "sd_scripts": (Quantization.NONE,),
            },
        ),
        ArchitectureProfile(
            key="anima",
            family="anima",
            flavour="anima-v1",
            text_encoder="qwen3_06b",
            latent_format="anima_latent",
            target_modules=("transformer_blocks.*.attn.*", "transformer_blocks.*.mlp.*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=16,
            supported_trainers={
                "simpletuner": SupportLevel.EXPERIMENTAL,
                "ai_toolkit": SupportLevel.SUPPORTED,
                "sd_scripts": SupportLevel.SUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "ai_toolkit": (Quantization.NONE, Quantization.NF4),
                "sd_scripts": (Quantization.NONE,),
            },
        ),
        ArchitectureProfile(
            key="hunyuan_image",
            family="hunyuan_image",
            flavour="image-base",
            text_encoder="llm+clip",
            latent_format="hunyuan_image_latent",
            target_modules=("double_blocks.*.img_attn.*", "single_blocks.*.attn.*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=32,
            supported_trainers={
                "simpletuner": SupportLevel.UNSUPPORTED,
                "ai_toolkit": SupportLevel.EXPERIMENTAL,
                "sd_scripts": SupportLevel.SUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "ai_toolkit": (Quantization.NONE, Quantization.NF4),
                "sd_scripts": (Quantization.NONE,),
            },
        ),
        ArchitectureProfile(
            key="krea2",
            family="krea2",
            flavour="krea2-image",
            text_encoder="model-specific",
            latent_format="krea2-latent",
            target_modules=("transformer_blocks.*.attn.*",),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=32,
            supported_trainers={
                "simpletuner": SupportLevel.SUPPORTED,
                "ai_toolkit": SupportLevel.SUPPORTED,
                "sd_scripts": SupportLevel.UNSUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "simpletuner": (Quantization.NONE, Quantization.FP8),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4),
            },
        ),
        ArchitectureProfile(
            key="hidream",
            family="hidream",
            flavour="hidream-i1",
            text_encoder="t5+llama+clip",
            latent_format="hidream-latent",
            target_modules=("double_blocks.*.img_attn.*", "single_blocks.*.attn.*"),
            training_schedule="flow_matching",
            text_encoder_trainable=False,
            minimum_vram_gib=48,
            supported_trainers={
                "simpletuner": SupportLevel.EXPERIMENTAL,
                "ai_toolkit": SupportLevel.EXPERIMENTAL,
                "sd_scripts": SupportLevel.UNSUPPORTED,
            },
            methods=dict(_LORA_METHODS),
            quantization={
                "simpletuner": (Quantization.NONE,),
                "ai_toolkit": (Quantization.NONE, Quantization.NF4),
            },
        ),
    )
    enriched = (replace(profile, features=dict(_LOW_VRAM_FEATURES)) for profile in profiles)
    return {profile.key: profile for profile in enriched}
