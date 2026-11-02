import random
import unittest

from src.comfyui_support_tools.shared.contracts.resolved_generation_parameters import (
    ResolvedGenerationParameters,
)
from scripts.backend.generation_parameter_resolver import (
    GenerationParameterResolver,
    ParameterSpec,
    default_parameter_registry,
)


class GenerationParameterResolverTests(unittest.TestCase):
    def test_resolves_fixed_values_without_changing_legacy_defaults(self):
        resolver = GenerationParameterResolver(random.Random(1))
        result = resolver.resolve(
            {
                "cfg": {"mode": "fixed", "value": 7},
                "steps": {"mode": "fixed", "value": 25},
                "resolution": {"mode": "fixed", "value": {"width": 960, "height": 1280}},
                "sampler": {"mode": "fixed", "value": " Euler a "},
            }
        )
        self.assertIsInstance(result, ResolvedGenerationParameters)
        self.assertEqual(
            result.to_dict(),
            {
                "cfg": 7.0,
                "steps": 25,
                "resolution": {"width": 960, "height": 1280},
                "sampler": "Euler a",
            },
        )

    def test_resolves_ranges_and_candidates_once_per_call(self):
        resolver = GenerationParameterResolver(random.Random(4))
        config = {
            "cfg": {"mode": "range", "min": 4.0, "max": 9.0},
            "steps": {"mode": "range", "min": 10, "max": 20},
            "resolution": {
                "mode": "candidate",
                "values": [
                    {"width": 512, "height": 768},
                    {"width": 768, "height": 1024},
                ],
            },
            "sampler": {"mode": "candidate", "values": ["Euler a", "DPM++ 2M Karras"]},
        }
        results = [resolver.resolve(config) for _ in range(12)]
        self.assertTrue(all(4.0 <= item.cfg <= 9.0 for item in results))
        self.assertTrue(all(10 <= item.steps <= 20 for item in results))
        self.assertEqual({item.width for item in results}, {512, 768})
        self.assertEqual({item.sampler for item in results}, {"Euler a", "DPM++ 2M Karras"})

    def test_rejects_invalid_ranges_and_empty_candidates(self):
        resolver = GenerationParameterResolver(random.Random(2))
        with self.assertRaisesRegex(ValueError, "minimum exceeds maximum"):
            resolver.resolve(self._configuration(cfg={"mode": "range", "min": 9, "max": 4}))
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            resolver.resolve(self._configuration(sampler={"mode": "candidate", "values": []}))
        with self.assertRaisesRegex(ValueError, "between 0.0 and 50.0"):
            resolver.resolve(self._configuration(cfg={"mode": "range", "min": -1, "max": 8}))
        with self.assertRaisesRegex(ValueError, "non-empty text"):
            resolver.resolve(
                self._configuration(sampler={"mode": "candidate", "values": ["Euler a", " "]})
            )

    def test_rejects_invalid_dimensions_and_unsupported_sampler_range(self):
        resolver = GenerationParameterResolver(random.Random(3))
        with self.assertRaisesRegex(ValueError, "multiple of 8"):
            resolver.resolve(
                self._configuration(
                    resolution={
                        "mode": "fixed",
                        "value": {"width": 65, "height": 512},
                    }
                )
            )
        with self.assertRaisesRegex(ValueError, "sampler mode"):
            resolver.resolve(self._configuration(sampler={"mode": "range", "min": 1, "max": 2}))

    def test_registered_seed_scheduler_and_custom_backend_parameter(self):
        registry = default_parameter_registry()
        registry.register(ParameterSpec("seed", "integer", 0, 2**32 - 1))
        registry.register(ParameterSpec("scheduler", "choice", choices=("normal", "karras")))
        registry.register(ParameterSpec("foo_strength", "number", 0.0, 2.0))
        registry.register(
            ParameterSpec("denoise", "number", 0.0, 1.0, namespace="comfyui", required=False)
        )
        configuration = self._configuration(
            seed={"mode": "fixed", "value": 12345},
            scheduler={"mode": "candidate", "values": ["karras"]},
            foo_strength={"mode": "range", "min": 0.5, "max": 0.5},
            comfyui={"denoise": {"mode": "fixed", "value": 0.7}},
        )
        result = GenerationParameterResolver(random.Random(9), registry).resolve(configuration)
        self.assertEqual(result.to_dict()["parameters"]["seed"], 12345)
        self.assertEqual(result.to_dict()["parameters"]["scheduler"], "karras")
        self.assertEqual(result.to_dict()["parameters"]["foo_strength"], 0.5)
        self.assertEqual(result.to_dict()["backend_parameters"]["comfyui"]["denoise"], 0.7)
        schema = {item["name"]: item for item in registry.schema()}
        self.assertEqual(schema["foo_strength"]["type"], "number")
        self.assertEqual(schema["denoise"]["namespace"], "comfyui")
        invalid_scheduler = dict(configuration)
        invalid_scheduler["scheduler"] = {
            "mode": "candidate",
            "values": ["unsupported"],
        }
        with self.assertRaisesRegex(ValueError, "configured choices"):
            GenerationParameterResolver(random.Random(9), registry).resolve(invalid_scheduler)

    @staticmethod
    def _configuration(**overrides):
        result = {
            "cfg": {"mode": "fixed", "value": 7.0},
            "steps": {"mode": "fixed", "value": 25},
            "resolution": {"mode": "fixed", "value": {"width": 512, "height": 512}},
            "sampler": {"mode": "fixed", "value": "Euler a"},
        }
        result.update(overrides)
        return result


if __name__ == "__main__":
    unittest.main()
