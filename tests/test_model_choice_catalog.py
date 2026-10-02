from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import scripts.context as app_context


class _Catalog:
    def query_choices(self, _base_url, _request_get):
        return {
            "checkpoints": ["sdxl/api-checkpoint.safetensors"],
            "unets": ["flux/api-unet.safetensors"],
            "loras": ["sdxl/api-style.safetensors"],
            "vaes": ["sdxl/api-vae.safetensors"],
            "upscalers": [],
            "samplers": [],
        }, []


def _write_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("model", encoding="utf-8")


class ModelChoiceCatalogTests(unittest.TestCase):
    def test_load_backend_choices_merges_local_and_api_per_model_kind(self):
        local = {
            "checkpoints": ["sdxl/local-checkpoint.safetensors"],
            "unets": ["flux/local-unet.safetensors"],
            "loras": ["sdxl/local-style.safetensors"],
            "vaes": ["sdxl/local-vae.safetensors"],
            "upscalers": [],
            "samplers": [],
            "flows": [],
        }
        with (
            patch.object(app_context, "_local_backend_choices", return_value=local),
            patch.object(app_context, "RUNTIME_BACKEND", "comfyui"),
            patch.object(app_context, "requests", SimpleNamespace(get=lambda *_a, **_kw: None)),
            patch(
                "scripts.backend.generation_backend_catalog_factory.create_generation_backend_catalog",
                return_value=_Catalog(),
            ),
        ):
            choices, warnings = app_context.load_backend_choices("http://localhost:8188", query_api=True)

        self.assertEqual(choices["checkpoints"], [
            "sdxl/api-checkpoint.safetensors", "sdxl/local-checkpoint.safetensors",
        ])
        self.assertEqual(choices["unets"], ["flux/api-unet.safetensors", "flux/local-unet.safetensors"])
        self.assertEqual(choices["loras"], ["sdxl/api-style.safetensors", "sdxl/local-style.safetensors"])
        self.assertEqual(warnings, [])

    def test_default_models_root_is_user_data_input_and_legacy_input_models_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with (
                patch.object(app_context, "APP_DIR", root),
                patch.object(app_context, "USER_DATA_FILE", root / "missing" / "paths.json"),
                patch.object(app_context, "LEGACY_USER_DATA_FILE", root / "missing-legacy.json"),
            ):
                defaults = app_context._load_user_paths()

            self.assertEqual(Path(defaults["models_root"]), root / "user_data" / "input" / "models")
            self.assertEqual(Path(defaults["checkpoints"]), root / "user_data" / "input" / "models" / "checkpoints")

            config = root / "paths.json"
            config.write_text('{"input_models": "D:/models/shared"}', encoding="utf-8")
            with (
                patch.object(app_context, "USER_DATA_FILE", config),
                patch.object(app_context, "LEGACY_USER_DATA_FILE", root / "missing-legacy.json"),
            ):
                migrated = app_context._load_user_paths()
            self.assertEqual(migrated["models_root"], "D:/models/shared")
            self.assertEqual(Path(migrated["checkpoints"]), Path("D:/models/shared") / "checkpoints")


    def test_a1111_catalog_includes_legacy_model_directories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            legacy_models = root / "models"
            legacy_checkpoints = root / "checkpoints"
            _write_file(legacy_checkpoints / "sd15" / "old.safetensors")
            _write_file(legacy_models / "Lora" / "sdxl" / "style.safetensors")
            _write_file(legacy_models / "VAE" / "sdxl" / "vae.safetensors")
            with (
                patch.object(app_context, "RUNTIME_BACKEND", "a1111"),
                patch.object(app_context, "MODELS_DIR", root / "new_models"),
                patch.object(app_context, "CHECKPOINTS_DIR", root / "new_models" / "checkpoints"),
                patch.object(app_context, "LEGACY_MODELS_DIR", legacy_models),
                patch.object(app_context, "LEGACY_CHECKPOINTS_DIRS", (legacy_models / "checkpoints", legacy_checkpoints)),
                patch.object(app_context, "A1111_DIR", root / "webui"),
                patch.object(app_context, "RUNTIME_DIR", root / "webui"),
            ):
                choices = app_context._local_backend_choices()

        self.assertEqual(choices["checkpoints"], ["sd15/old.safetensors"])
        self.assertEqual(choices["loras"], ["sdxl/style.safetensors"])
        self.assertEqual(choices["vaes"], ["sdxl/vae.safetensors"])


    def test_primary_base_choices_include_unets_only_for_comfyui(self):
        choices = {"checkpoints": ["checkpoint.safetensors"], "unets": ["unet.safetensors"]}
        with patch.object(app_context, "RUNTIME_BACKEND", "comfyui"):
            comfy_choices = app_context.base_model_choices(choices)
        with patch.object(app_context, "RUNTIME_BACKEND", "a1111"):
            a1111_choices = app_context.base_model_choices(choices)

        self.assertEqual(comfy_choices, ["checkpoint.safetensors", "unet.safetensors"])
        self.assertEqual(a1111_choices, ["checkpoint.safetensors"])

    def test_local_model_folders_are_kept_in_separate_categories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            models_root = root / "shared_models"
            runtime_root = root / "ComfyUI"
            checkpoints_root = models_root / "checkpoints"
            _write_file(checkpoints_root / "sdxl" / "base.safetensors")
            _write_file(models_root / "diffusion_models" / "flux" / "dev.safetensors")
            _write_file(models_root / "Lora" / "sdxl" / "style.safetensors")
            _write_file(models_root / "VAE" / "sdxl" / "vae.safetensors")
            legacy_models_root = root / "models"
            _write_file(legacy_models_root / "checkpoints" / "sd15" / "old.safetensors")
            _write_file(legacy_models_root / "Lora" / "sd15" / "old_style.safetensors")
            (legacy_models_root / "flows").mkdir(parents=True)
            (legacy_models_root / "flows" / "old.json").write_text("{}", encoding="utf-8")
            _write_file(runtime_root / "models" / "loras" / "flux" / "style.safetensors")

            with (
                patch.object(app_context, "MODELS_DIR", models_root),
                patch.object(app_context, "CHECKPOINTS_DIR", checkpoints_root),
                patch.object(app_context, "LEGACY_MODELS_DIR", legacy_models_root),
                patch.object(app_context, "LEGACY_CHECKPOINTS_DIRS", (legacy_models_root / "checkpoints", root / "old_checkpoints")),
                patch.object(app_context, "RUNTIME_DIR", runtime_root),
                patch.object(app_context, "COMFY_FLOWS_DIR", root / "flows"),
                patch.object(app_context, "RUNTIME_BACKEND", "comfyui"),
            ):
                choices = app_context._local_backend_choices()

        self.assertEqual(choices["checkpoints"], ["sdxl/base.safetensors", "sd15/old.safetensors"])
        self.assertEqual(choices["unets"], ["flux/dev.safetensors"])
        self.assertEqual(choices["loras"], ["sdxl/style.safetensors", "sd15/old_style.safetensors", "flux/style.safetensors"])
        self.assertEqual(choices["vaes"], ["sdxl/vae.safetensors"])
        self.assertEqual(choices["flows"], ["old.json"])


if __name__ == "__main__":
    unittest.main()
