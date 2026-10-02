from __future__ import annotations

import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import context
from scripts.backend.local_model_evidence import _model_roots, classify_local_model_choice
from scripts.backend.model_choice_classification import classify_base_model_choice
from scripts.backend.prompt_lora_compatibility import validate_prompt_loras
from src.comfyui_support_tools.shared.model_identity import ModelFamily, ModelKind


def _write_header(path: Path, family: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = json.dumps({"__metadata__": {"ss_base_model_version": family}}).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header)


def _write_shapes(path: Path, shapes: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = json.dumps({key: {"shape": list(shape)} for key, shape in shapes.items()}).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(header)) + header)


class LocalModelEvidenceTests(unittest.TestCase):
    def test_structure_only_checkpoint_and_lora_mismatch_stops_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_shapes(root / "base.safetensors", {
                "model.diffusion_model.input_blocks.0.0.weight": (320, 4, 3, 3),
                "model.diffusion_model.input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight": (640, 768),
            })
            name = "lora_unet_input_blocks_4_1_transformer_blocks_0_attn2_to_k"
            _write_shapes(root / "style.safetensors", {
                name + ".lora_down.weight": (16, 2048), name + ".lora_up.weight": (640, 16),
            })
            with patch("scripts.backend.local_model_evidence._model_roots", return_value=[root]):
                logs = []
                with self.assertRaisesRegex(ValueError, "生成を中止"):
                    validate_prompt_loras(
                        "<lora:style:1>", "base.safetensors",
                        {"checkpoints": ["base.safetensors"], "loras": ["style.safetensors"]}, logs.append,
                    )
                self.assertIn("tensor", logs[0])

    def test_replaced_structure_only_model_invalidates_cached_classification(self):
        path = self.root / "base.safetensors"
        shapes = {
            "model.diffusion_model.input_blocks.0.0.weight": (320, 4, 3, 3),
            "model.diffusion_model.input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight": (640, 768),
        }
        _write_shapes(path, shapes)
        self.assertEqual(classify_local_model_choice(path.name, ModelKind.CHECKPOINT).family, ModelFamily.SD_1_5)
        before = path.stat()
        shapes["model.diffusion_model.input_blocks.4.1.transformer_blocks.0.attn2.to_k.weight"] = (640, 2048)
        _write_shapes(path, shapes)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        self.assertEqual(classify_local_model_choice(path.name, ModelKind.CHECKPOINT).family, ModelFamily.SDXL)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        roots = patch("scripts.backend.local_model_evidence._model_roots", return_value=[self.root])
        self.roots = roots.start()
        self.addCleanup(roots.stop)

    def test_catalog_classifier_uses_metadata_for_generic_filename(self):
        _write_header(self.root / "base.safetensors", "sdxl_base_v1-0")
        result = classify_base_model_choice("base.safetensors", {"checkpoints": ["base.safetensors"]})
        self.assertEqual(result.family, ModelFamily.SDXL)
        self.assertIn("metadata ss_base_model_version", result.family_reason)

    def test_a1111_checkpoint_display_hash_resolves_local_header(self):
        _write_header(self.root / "base.safetensors", "sdxl")
        name = "base.safetensors [012345abcd]"
        result = classify_base_model_choice(name, {"checkpoints": [name]})
        self.assertEqual(result.family, ModelFamily.SDXL)

    def test_a1111_lora_stem_finds_unique_nested_file_and_metadata(self):
        _write_header(self.root / "base.safetensors", "flux1")
        _write_header(self.root / "nested" / "style.safetensors", "sdxl")
        with self.assertRaisesRegex(ValueError, "生成を中止"):
            validate_prompt_loras(
                "<lora:style:1>", "base.safetensors",
                {"checkpoints": ["base.safetensors"], "loras": ["style", "nested/style.safetensors"]},
                lambda _message: None,
            )

    def test_a1111_stem_with_multiple_local_matches_remains_unknown(self):
        _write_header(self.root / "sdxl" / "style.safetensors", "sdxl")
        _write_header(self.root / "flux" / "style.safetensors", "flux1")
        result = classify_local_model_choice("style", ModelKind.LORA)
        self.assertEqual(result.family, ModelFamily.UNKNOWN)

    def test_dotted_lora_api_name_is_an_alias_not_a_file_extension(self):
        _write_header(self.root / "base.safetensors", "flux1")
        _write_header(self.root / "style.v1.2.safetensors", "sdxl")
        with self.assertRaisesRegex(ValueError, "生成を中止"):
            validate_prompt_loras(
                "<lora:style.v1.2:1>", "base.safetensors",
                {"checkpoints": ["base.safetensors"], "loras": ["style.v1.2", "style.v1.2.safetensors"]},
                lambda _message: None,
            )

    def test_api_alias_and_local_filename_use_same_metadata_for_compatibility(self):
        _write_header(self.root / "base.safetensors", "flux1")
        _write_header(self.root / "style.safetensors", "sdxl")
        logs = []
        with self.assertRaisesRegex(ValueError, "生成を中止"):
            validate_prompt_loras(
                "<lora:style:1>", "base.safetensors",
                {"checkpoints": ["base.safetensors"], "loras": ["style", "style.safetensors"]}, logs.append,
            )
        self.assertIn("extensionless API alias", logs[0])

    def test_metadata_mismatch_stops_prompt_generation_for_generic_names(self):
        _write_header(self.root / "base.safetensors", "flux1")
        _write_header(self.root / "style.safetensors", "sdxl_base_v1-0")
        logs = []
        with self.assertRaisesRegex(ValueError, "生成を中止"):
            validate_prompt_loras(
                "<lora:style:1>", "base.safetensors",
                {"checkpoints": ["base.safetensors"], "loras": ["style.safetensors"]}, logs.append,
            )
        self.assertIn("[incompatible]", logs[0])
        self.assertIn("metadata", logs[0])

    def test_duplicate_distinct_local_files_keep_family_unknown(self):
        other = self.root / "other"
        self.roots.return_value = [self.root, other]
        _write_header(self.root / "base.safetensors", "sdxl")
        _write_header(other / "base.safetensors", "flux1")
        result = classify_local_model_choice("base.safetensors", ModelKind.CHECKPOINT)
        self.assertEqual(result.family, ModelFamily.UNKNOWN)
        self.assertIn("ambiguous", result.family_reason)

    def test_duplicate_roots_do_not_make_one_file_ambiguous(self):
        self.roots.return_value = [self.root, self.root / "."]
        _write_header(self.root / "base.safetensors", "sdxl")
        self.assertEqual(classify_local_model_choice("base.safetensors", ModelKind.CHECKPOINT).family, ModelFamily.SDXL)

    def test_broken_header_keeps_path_evidence_and_reports_problem(self):
        path = self.root / "sdxl" / "base.safetensors"
        path.parent.mkdir()
        path.write_bytes(b"broken")
        result = classify_local_model_choice("sdxl/base.safetensors", ModelKind.CHECKPOINT)
        self.assertEqual(result.family, ModelFamily.SDXL)
        self.assertIn("metadata unavailable", result.family_reason)

    def test_replacing_model_invalidates_header_cache(self):
        path = self.root / "base.safetensors"
        _write_header(path, "flux1")
        self.assertEqual(classify_local_model_choice(path.name, ModelKind.CHECKPOINT).family, ModelFamily.FLUX)
        before = path.stat()
        _write_header(path, "sdxl_base_v1-0")
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000))
        self.assertEqual(classify_local_model_choice(path.name, ModelKind.CHECKPOINT).family, ModelFamily.SDXL)

    def test_catalog_name_cannot_read_metadata_outside_model_roots(self):
        _write_header(self.root / "base.safetensors", "sdxl")
        self.roots.return_value = [self.root / "sub"]
        result = classify_local_model_choice("../base.safetensors", ModelKind.CHECKPOINT)
        self.assertEqual(result.family, ModelFamily.UNKNOWN)

    def test_legacy_lora_root_is_resolved_from_configuration(self):
        _write_header(self.root / "legacy" / "Lora" / "style.safetensors", "sdxl")
        self.roots.side_effect = _model_roots
        with (
            patch.object(context, "MODELS_DIR", self.root / "shared"),
            patch.object(context, "LEGACY_MODELS_DIR", self.root / "legacy"),
            patch.object(context, "RUNTIME_DIR", self.root / "backend"),
        ):
            result = classify_local_model_choice("style.safetensors", ModelKind.LORA)
        self.assertEqual(result.family, ModelFamily.SDXL)


if __name__ == "__main__":
    unittest.main()
