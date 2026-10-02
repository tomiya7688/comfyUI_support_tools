from __future__ import annotations

import unittest

from src.comfyui_support_tools.shared.model_identity import ModelFamily, ModelKind, classify_model


def _unet(width: int, prefix: str = "model.diffusion_model.") -> dict:
    return {
        prefix + "input_blocks.0.0.weight": (320, 4, 3, 3),
        prefix + "input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight": (640, width),
        prefix + "input_blocks.4.1.transformer_blocks.0.attn2.to_v.weight": (640, width),
    }


def _lora(width: int) -> dict:
    name = "lora_unet_input_blocks_4_1_transformer_blocks_0_attn2_to_k"
    return {name + ".lora_down.weight": (16, width), name + ".lora_up.weight": (640, 16)}


def _flux(prefix: str = "") -> dict:
    return {prefix + key: shape for key, shape in {
        "img_in.weight": (3072, 64), "txt_in.weight": (3072, 4096),
        "double_blocks.0.img_attn.qkv.weight": (9216, 3072),
        "double_blocks.0.txt_attn.qkv.weight": (9216, 3072),
    }.items()}


def _anima(prefix: str = "net.") -> dict:
    return {prefix + key: shape for key, shape in {
        "blocks.0.mlp.layer1.weight": (8192, 2048),
        "x_embedder.proj.1.weight": (2048, 68),
        "llm_adapter.blocks.0.cross_attn.q_proj.weight": (1024, 1024),
    }.items()}


class TensorModelFamilyTests(unittest.TestCase):
    def test_sd_families_from_unet_context_shapes_with_generic_filename(self):
        for width, family in [(768, ModelFamily.SD_1_5), (2048, ModelFamily.SDXL)]:
            for prefix in ["", "model.diffusion_model.", "diffusion_model.", "unet."]:
                with self.subTest(width=width, prefix=prefix):
                    result = classify_model("generic.safetensors", tensor_shapes=_unet(width, prefix), declared_kind="checkpoint")
                    self.assertEqual(result.family, family)
                    self.assertEqual(result.kind, ModelKind.CHECKPOINT)
                    self.assertIn("tensor", result.family_reason)
                    self.assertIn(str(width), result.family_reason)

    def test_diffusers_unet_layout_is_supported(self):
        shapes = {
            "unet.conv_in.weight": (320, 4, 3, 3),
            "unet.down_blocks.1.attentions.0.transformer_blocks.0.attn2.to_k.weight": (640, 2048),
        }
        self.assertEqual(classify_model("generic", tensor_shapes=shapes).family, ModelFamily.SDXL)

    def test_lora_pairs_supply_unet_architecture_evidence(self):
        for width, family in [(768, ModelFamily.SD_1_5), (2048, ModelFamily.SDXL)]:
            with self.subTest(width=width):
                result = classify_model("generic", tensor_shapes=_lora(width), declared_kind="lora")
                self.assertEqual(result.family, family)
                self.assertEqual(result.kind, ModelKind.LORA)

    def test_peft_lora_pairs_are_supported(self):
        key = "base_model.model.unet.down_blocks.1.attentions.0.transformer_blocks.0.attn2.to_v"
        shapes = {key + ".lora_A.weight": (8, 2048), key + ".lora_B.weight": (640, 8)}
        self.assertEqual(classify_model("generic", tensor_shapes=shapes).family, ModelFamily.SDXL)

    def test_incomplete_or_mismatched_lora_pair_is_not_family_evidence(self):
        shapes = _lora(2048)
        up = next(key for key in shapes if "lora_up" in key)
        for replacement in [None, (640, 8)]:
            with self.subTest(replacement=replacement):
                candidate = dict(shapes)
                if replacement is None:
                    candidate.pop(up)
                else:
                    candidate[up] = replacement
                self.assertEqual(classify_model("generic", tensor_shapes=candidate).family, ModelFamily.UNKNOWN)

    def test_only_text_encoder_or_unet_self_attention_does_not_infer_family(self):
        for shapes in [
            {"text_encoder.encoder.layers.0.attn2.to_k.weight": (640, 2048)},
            {"lora_te1_encoder.layers.0.attn2.to_k.lora_down.weight": (16, 768)},
            {"model.diffusion_model.input_blocks.0.0.weight": (320, 4, 3, 3),
             "model.diffusion_model.input_blocks.4.1.transformer_blocks.0.attn1.to_k.weight": (640, 768)},
        ]:
            with self.subTest(shapes=shapes):
                self.assertEqual(classify_model("generic", tensor_shapes=shapes).family, ModelFamily.UNKNOWN)

    def test_mixed_or_unsupported_context_dimensions_remain_unknown(self):
        mixed = _unet(768)
        mixed["model.diffusion_model.output_blocks.1.1.transformer_blocks.0.attn2.to_k.weight"] = (640, 2048)
        for shapes in [mixed, _unet(1024)]:
            with self.subTest(shapes=shapes):
                result = classify_model("sdxl/generic", tensor_shapes=shapes)
                self.assertEqual(result.family, ModelFamily.UNKNOWN)
                self.assertIn("Conflicting", result.family_reason)

    def test_tensor_evidence_conflicting_with_metadata_or_filename_is_unknown(self):
        for name, metadata in [("sdxl/generic", None), ("generic", {"ss_base_model_version": "sdxl"})]:
            with self.subTest(name=name):
                result = classify_model(name, metadata=metadata, tensor_shapes=_unet(768))
                self.assertEqual(result.family, ModelFamily.UNKNOWN)
                self.assertIn("tensor", result.family_reason)

    def test_anima_backbone_and_adapter_must_match_under_one_prefix(self):
        for prefix in ["", "net.", "model.diffusion_model."]:
            with self.subTest(prefix=prefix):
                self.assertEqual(classify_model("generic", tensor_shapes=_anima(prefix)).family, ModelFamily.ANIMA)
        shapes = _anima()
        shapes.pop("net.llm_adapter.blocks.0.cross_attn.q_proj.weight")
        self.assertEqual(classify_model("generic", tensor_shapes=shapes).family, ModelFamily.UNKNOWN)
        self.assertEqual(classify_model("anima/generic", tensor_shapes=shapes).family, ModelFamily.UNKNOWN)
        shapes["llm_adapter.blocks.0.cross_attn.q_proj.weight"] = (1024, 1024)
        self.assertEqual(classify_model("generic", tensor_shapes=shapes).family, ModelFamily.UNKNOWN)

    def test_flux_base_signature_and_exclusion_of_chroma_layout(self):
        shapes = _flux("model.diffusion_model.")
        self.assertEqual(classify_model("generic", tensor_shapes=shapes).family, ModelFamily.FLUX)
        shapes["model.diffusion_model.distilled_guidance_layer.in_proj.weight"] = (3072, 256)
        result = classify_model("flux/generic", tensor_shapes=shapes)
        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertIn("Chroma", result.family_reason)

    def test_changed_flux_projection_or_mixed_transformers_remains_unknown(self):
        changed = _flux()
        changed["txt_in.weight"] = (3072, 15360)
        self.assertEqual(classify_model("generic", tensor_shapes=changed).family, ModelFamily.UNKNOWN)
        mixed = {**_flux(), **_anima()}
        self.assertEqual(classify_model("generic", tensor_shapes=mixed).family, ModelFamily.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
