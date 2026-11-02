"""Infer architecture evidence from tensor names and shapes, without weights."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence


_FULL_CONTEXT = re.compile(
    r"^(?P<prefix>(?:model\.diffusion_model\.|diffusion_model\.|unet\.)?)"
    r"(?:input_blocks|output_blocks|middle_block|down_blocks|up_blocks|mid_block)"
    r"\..*\.attn2\.to_[kv]\.weight$"
)
_LORA_CONTEXT = re.compile(
    r"^lora_unet_(?:input_blocks|output_blocks|middle_block|down_blocks|up_blocks|mid_block)"
    r"_.*_attn2_to_[kv]\.lora_down\.weight$"
    r"|^(?:base_model\.model\.)?(?:unet\.)?"
    r"(?:input_blocks|output_blocks|middle_block|down_blocks|up_blocks|mid_block)"
    r"\..*\.attn2\.to_[kv]\.(?:lora_down|lora_A)\.weight$"
)
_TRANSFORMER_PREFIXES = ("", "model.diffusion_model.", "diffusion_model.", "net.", "transformer.")


# {
#   責務: [_shape: shape mapping内の正の整数dimension tupleだけを受理する]
#   処理: [欠落・不正型・非正整数を空tupleに変換する]
#   引数: [shapes: tensor name-to-shape mapping, name: lookupするtensor名]
#   戻り値: [shape: 有効shape tupleまたは空tuple]
# }
def _shape(shapes: Mapping[str, Sequence[int]], name: str) -> tuple[int, ...]:
    value = shapes.get(name, ())
    if not isinstance(value, (list, tuple)) or any(
        type(dimension) is not int or dimension <= 0 for dimension in value
    ):
        return ()
    return tuple(value)


# {
#   責務: [_has_sd_input: 既知のSD input convolution shape signatureを検出する]
#   処理: [input_blocks.0.0.weight/conv_in.weightのprefix付き候補を照合する]
#   引数: [shapes: tensor shapes, prefix: tensor name prefix]
#   戻り値: [matched: input convolution signatureがあればtrue]
# }
def _has_sd_input(shapes: Mapping[str, Sequence[int]], prefix: str) -> bool:
    for name in ("input_blocks.0.0.weight", "conv_in.weight"):
        shape = _shape(shapes, prefix + name)
        if len(shape) == 4 and shape[0] == 320 and shape[1] in {4, 8, 9} and shape[2:] == (3, 3):
            return True
    return False


# {
#   責務: [_paired_lora: down projectionに対応するup projection signatureを確認する]
#   処理: [lora_down/lora_A名を対応するlora_up/lora_Bへ変換しrank/dimensionを照合する]
#   引数: [shapes: tensor shapes, name: down tensor名, down: down shape]
#   戻り値: [matched: 対応up tensor shapeが認識範囲ならtrue]
# }
def _paired_lora(shapes: Mapping[str, Sequence[int]], name: str, down: tuple[int, ...]) -> bool:
    up_name = name.replace(".lora_down.weight", ".lora_up.weight").replace(
        ".lora_A.weight", ".lora_B.weight"
    )
    up = _shape(shapes, up_name)
    return len(up) == 2 and up[1] == down[0] and up[0] in {320, 640, 1280}


# {
#   責務: [_unet_signals: UNet cross-attention tensor shapeからSD family evidenceを抽出する]
#   処理: [full checkpointまたはpaired LoRA signaturesを集計しdimension conflict/unknownを保持する]
#   引数: [shapes: tensor name-to-shape mapping]
#   戻り値: [family/reason evidence list; unsupported/conflicting shapesはunknown evidence]
# }
def _unet_signals(shapes: Mapping[str, Sequence[int]]) -> list[tuple[str, str]]:
    entries = []
    for name in shapes:
        shape = _shape(shapes, name)
        if len(shape) != 2:
            continue
        full = _FULL_CONTEXT.fullmatch(name)
        if full and shape[0] in {320, 640, 1280} and _has_sd_input(shapes, full.group("prefix")):
            entries.append((name, shape[1]))
        elif _LORA_CONTEXT.fullmatch(name) and _paired_lora(shapes, name, shape):
            entries.append((name, shape[1]))
    dimensions = {dimension for _, dimension in entries}
    if not dimensions:
        return []
    if len(dimensions) != 1:
        return [
            ("unknown", f"Tensor UNet cross-attention dimensions conflict: {sorted(dimensions)}.")
        ]
    dimension = next(iter(dimensions))
    family = {768: "sd1.5", 2048: "sdxl"}.get(dimension)
    if family is None:
        return [
            (
                "unknown",
                f"Tensor UNet cross-attention dimension {dimension} is not a supported SD1.x/SDXL base signature.",
            )
        ]
    return [
        (
            family,
            f"tensor {entries[0][0]!r} has cross-attention input dimension {dimension}; architectural family evidence, not an exact model release.",
        )
    ]


# {
#   責務: [_transformer_signals: transformer tensor layoutからANIMA/FLUX family evidenceを抽出する]
#   処理: [既知prefixのsignatureを照合し、ambiguous Chroma/Cosmos-like layoutはunknownとして返す]
#   引数: [shapes: tensor name-to-shape mapping]
#   戻り値: [family/reason evidence list]
# }
def _transformer_signals(shapes: Mapping[str, Sequence[int]]) -> list[tuple[str, str]]:
    signals = []
    for prefix in _TRANSFORMER_PREFIXES:
        anima = {
            "blocks.0.mlp.layer1.weight": (8192, 2048),
            "x_embedder.proj.1.weight": (2048, 68),
        }
        if all(_shape(shapes, prefix + key) == value for key, value in anima.items()):
            if _shape(shapes, prefix + "llm_adapter.blocks.0.cross_attn.q_proj.weight") == (
                1024,
                1024,
            ):
                signals.append(
                    (
                        "anima",
                        f"tensor layout at {prefix!r} combines the Anima 2B backbone and LLM adapter signatures.",
                    )
                )
            else:
                signals.append(
                    (
                        "unknown",
                        "Cosmos-like tensor backbone lacks the supported Anima LLM adapter signature.",
                    )
                )
        flux = {
            "img_in.weight": (3072, 64),
            "txt_in.weight": (3072, 4096),
            "double_blocks.0.img_attn.qkv.weight": (9216, 3072),
            "double_blocks.0.txt_attn.qkv.weight": (9216, 3072),
        }
        if all(_shape(shapes, prefix + key) == value for key, value in flux.items()):
            if any(key.startswith(prefix + "distilled_guidance_layer.") for key in shapes):
                signals.append(
                    (
                        "unknown",
                        "Flux-like tensor layout also contains Chroma-specific distilled guidance; family is ambiguous.",
                    )
                )
            else:
                signals.append(
                    (
                        "flux",
                        f"tensor layout at {prefix!r} matches FLUX.1 base image/text projections and double-stream QKV shapes.",
                    )
                )
    return signals


# {
#   責務: [tensor_family_signals: weightsを読み込まずshape mappingからfamily evidenceを返す]
#   処理: [UNetとtransformerの独立signalを連結し、family conflictの解決はcallerへ委ねる]
#   引数: [shapes: tensor name-to-shape mappingまたはNone]
#   戻り値: [family/reason evidence list; 入力が空なら空list]
# }
def tensor_family_signals(shapes: Mapping[str, Sequence[int]] | None) -> list[tuple[str, str]]:
    """Return independent family signals; the caller resolves conflicting evidence."""
    if not shapes:
        return []
    return _unet_signals(shapes) + _transformer_signals(shapes)
