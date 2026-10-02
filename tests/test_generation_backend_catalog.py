from __future__ import annotations

import unittest

from scripts.backend.a1111_backend_catalog import A1111BackendCatalog
from scripts.backend.comfyui_backend_catalog import ComfyUIBackendCatalog
from scripts.backend.generation_backend_catalog_factory import create_generation_backend_catalog


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class GenerationBackendCatalogTests(unittest.TestCase):
    def test_a1111_queries_all_catalogs_and_normalizes_api_url(self):
        payloads = {
            "sd-models": [{"title": "checkpoint.safetensors"}],
            "loras": [{"name": "character/style"}],
            "sd-vae": [{"model_name": "vae.safetensors"}],
            "upscalers": [{"name": "4x-UltraSharp"}],
            "samplers": [{"name": "Euler a"}],
        }
        calls = []

        def get(url, timeout):
            calls.append((url, timeout))
            endpoint = url.rsplit("/", 1)[-1]
            return FakeResponse(payloads[endpoint])

        choices, warnings = A1111BackendCatalog().query_choices(
            "http://localhost:7860/sdapi/v1/txt2img", get
        )

        self.assertEqual(choices, {
            "checkpoints": ["checkpoint.safetensors"],
            "unets": [],
            "loras": ["character/style"],
            "vaes": ["vae.safetensors"],
            "upscalers": ["4x-UltraSharp"],
            "samplers": ["Euler a"],
        })
        self.assertEqual(warnings, [])
        self.assertEqual(calls[0], ("http://localhost:7860/sdapi/v1/sd-models", 5))

    def test_comfyui_reads_choices_from_object_info(self):
        values = {
            "CheckpointLoaderSimple": ("ckpt_name", ["model.safetensors"]),
            "UNETLoader": ("unet_name", ["diffusion_models/flux-dev.safetensors"]),
            "LoraLoader": ("lora_name", ["style.safetensors"]),
            "VAELoader": ("vae_name", ["vae.safetensors"]),
            "UpscaleModelLoader": ("model_name", ["upscale.pth"]),
            "KSampler": ("sampler_name", ["euler"]),
        }

        def get(url, timeout):
            node_name = url.rsplit("/", 1)[-1]
            field, choices = values[node_name]
            return FakeResponse({node_name: {"input": {"required": {field: [choices, {}]}}}})

        choices, warnings = ComfyUIBackendCatalog().query_choices("http://localhost:8188/", get)

        self.assertEqual(choices, {
            "checkpoints": ["model.safetensors"],
            "unets": ["diffusion_models/flux-dev.safetensors"],
            "loras": ["style.safetensors"],
            "vaes": ["vae.safetensors"],
            "upscalers": ["upscale.pth"],
            "samplers": ["euler"],
        })
        self.assertEqual(warnings, [])

    def test_endpoint_failure_is_reported_without_losing_other_results(self):
        def get(url, timeout):
            if url.endswith("/samplers"):
                raise RuntimeError("offline")
            if url.endswith("/loras"):
                return FakeResponse([{"name": "style"}])
            if url.endswith("/sd-models"):
                return FakeResponse([{"model_name": "checkpoint"}])
            if url.endswith("/sd-vae"):
                return FakeResponse([{"model_name": "vae"}])
            return FakeResponse([{"name": "upscaler"}])

        choices, warnings = A1111BackendCatalog().query_choices("http://localhost:7860", get)

        self.assertEqual(choices["checkpoints"], ["checkpoint"])
        self.assertEqual(choices["loras"], ["style"])
        self.assertEqual(choices["upscalers"], ["upscaler"])
        self.assertEqual(choices["samplers"], [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("samplers", warnings[0])

    def test_factory_rejects_unknown_backend(self):
        with self.assertRaises(ValueError):
            create_generation_backend_catalog("unknown")


if __name__ == "__main__":
    unittest.main()
