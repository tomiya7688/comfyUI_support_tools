"""Declarative profiles for efficient text-to-image model variants."""

from __future__ import annotations

from .contracts import FastModelProfile, GenerationIntent, ModelCapability, Quantization


# {
#   責務: [create_default_fast_model_profiles: FLUX.2 KleinとSanaの効率variantを登録する]
#   処理: [issue記載の対象familyをモデル名ベースで識別できるdescriptorとして返す]
#   引数: []
#   戻り値: [tuple[FastModelProfile, ...]: 拡張可能なbuilt-in descriptor]
#   注意: [VRAM要件は保守的な導入目安であり, 実測値や画質保証ではない]
# }
def create_default_fast_model_profiles() -> tuple[FastModelProfile, ...]:
    intents = frozenset(GenerationIntent)
    quantizations = frozenset(Quantization)
    return (
        FastModelProfile(
            profile_id="flux2_klein_4b_distilled",
            aliases=("flux2 klein 4b", "flux.2 klein 4b", "flux2-klein-4b"),
            minimum_vram_gib=8,
            minimum_ram_gib=16,
            intents=intents,
            quantizations=quantizations,
            steps=4,
            capabilities=frozenset({ModelCapability.TXT2IMG, ModelCapability.IMG2IMG}),
            minimum_vram_by_quantization=(
                (Quantization.FP8, 7),
                (Quantization.INT8, 6),
                (Quantization.INT4, 4),
            ),
        ),
        FastModelProfile(
            profile_id="flux2_klein_4b_base",
            aliases=("flux2 klein 4b base", "flux.2 klein 4b base"),
            minimum_vram_gib=12,
            minimum_ram_gib=24,
            intents=frozenset({GenerationIntent.ITERATION, GenerationIntent.BACKGROUND}),
            quantizations=quantizations,
            steps=30,
            capabilities=frozenset(
                {
                    ModelCapability.TXT2IMG,
                    ModelCapability.IMG2IMG,
                    ModelCapability.LORA_FINETUNE,
                }
            ),
            fast_route=False,
        ),
        FastModelProfile(
            profile_id="sana_sprint",
            aliases=("sana sprint", "sana-sprint"),
            minimum_vram_gib=8,
            minimum_ram_gib=16,
            intents=intents,
            quantizations=quantizations,
            steps=4,
            experimental=True,
            minimum_vram_by_quantization=(
                (Quantization.FP8, 7),
                (Quantization.INT8, 6),
                (Quantization.INT4, 4),
            ),
        ),
        FastModelProfile(
            profile_id="sana",
            aliases=("sana 1.5", "sana 1.6", "sana"),
            minimum_vram_gib=12,
            minimum_ram_gib=24,
            intents=intents,
            quantizations=quantizations,
            steps=12,
            experimental=True,
            minimum_vram_by_quantization=(
                (Quantization.FP8, 11),
                (Quantization.INT8, 9),
                (Quantization.INT4, 7),
            ),
        ),
    )
