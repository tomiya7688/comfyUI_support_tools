import random
import unittest

from src.comfyui_support_tools.shared.contracts.resolved_generation_parameters import ResolvedGenerationParameters
from scripts.backend.generation_parameter_resolver import GenerationParameterResolver


# {
#   責務: [GenerationParameterResolverTests: related test fixtures and cases for GenerationParameterResolver behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class GenerationParameterResolverTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_resolves_fixed_values_without_changing_legacy_defaults: verifies the behavior described by "resolves fixed values without changing legacy defaults",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for resolves fixed values without changing legacy defaults,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_resolves_fixed_values_without_changing_legacy_defaults(self):
        resolver = GenerationParameterResolver(random.Random(1))
        result = resolver.resolve({
            "cfg": {"mode": "fixed", "value": 7},
            "steps": {"mode": "fixed", "value": 25},
            "resolution": {"mode": "fixed", "value": {"width": 960, "height": 1280}},
            "sampler": {"mode": "fixed", "value": " Euler a "},
        })
        self.assertIsInstance(result, ResolvedGenerationParameters)
        self.assertEqual(result.to_dict(), {
            "cfg": 7.0,
            "steps": 25,
            "resolution": {"width": 960, "height": 1280},
            "sampler": "Euler a",
        })

    # {
    #   責務: [
    #     test_resolves_ranges_and_candidates_once_per_call: verifies the behavior described by "resolves ranges and candidates once per call",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for resolves ranges and candidates once per call,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_resolves_ranges_and_candidates_once_per_call(self):
        resolver = GenerationParameterResolver(random.Random(4))
        config = {
            "cfg": {"mode": "range", "min": 4.0, "max": 9.0},
            "steps": {"mode": "range", "min": 10, "max": 20},
            "resolution": {"mode": "candidate", "values": [
                {"width": 512, "height": 768}, {"width": 768, "height": 1024},
            ]},
            "sampler": {"mode": "candidate", "values": ["Euler a", "DPM++ 2M Karras"]},
        }
        results = [resolver.resolve(config) for _ in range(12)]
        self.assertTrue(all(4.0 <= item.cfg <= 9.0 for item in results))
        self.assertTrue(all(10 <= item.steps <= 20 for item in results))
        self.assertEqual({item.width for item in results}, {512, 768})
        self.assertEqual({item.sampler for item in results}, {"Euler a", "DPM++ 2M Karras"})

    # {
    #   責務: [
    #     test_rejects_invalid_ranges_and_empty_candidates: verifies the behavior described by "rejects invalid ranges and empty candidates",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for rejects invalid ranges and empty candidates,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_rejects_invalid_ranges_and_empty_candidates(self):
        resolver = GenerationParameterResolver(random.Random(2))
        with self.assertRaisesRegex(ValueError, "minimum exceeds maximum"):
            resolver.resolve(self._configuration(cfg={"mode": "range", "min": 9, "max": 4}))
        with self.assertRaisesRegex(ValueError, "non-empty list"):
            resolver.resolve(self._configuration(sampler={"mode": "candidate", "values": []}))
        with self.assertRaisesRegex(ValueError, "between 0.0 and 50.0"):
            resolver.resolve(self._configuration(cfg={"mode": "range", "min": -1, "max": 8}))
        with self.assertRaisesRegex(ValueError, "non-empty text"):
            resolver.resolve(self._configuration(sampler={"mode": "candidate", "values": ["Euler a", " "]}))

    # {
    #   責務: [
    #     test_rejects_invalid_dimensions_and_unsupported_sampler_range: verifies the behavior described by "rejects invalid dimensions and unsupported sampler range",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for rejects invalid dimensions and unsupported sampler range,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_rejects_invalid_dimensions_and_unsupported_sampler_range(self):
        resolver = GenerationParameterResolver(random.Random(3))
        with self.assertRaisesRegex(ValueError, "multiple of 8"):
            resolver.resolve(self._configuration(resolution={
                "mode": "fixed", "value": {"width": 65, "height": 512},
            }))
        with self.assertRaisesRegex(ValueError, "sampler mode"):
            resolver.resolve(self._configuration(sampler={"mode": "range", "min": 1, "max": 2}))

    # {
    #   責務: [_configuration: builds the baseline generation parameter mapping]
    #   処理: [1: apply supplied settings overrides to the base configuration, 2: return the fixture configuration]
    #   引数: [**overrides: **overrides passed to this helper (unspecified)]
    #   戻り値: [result: result value built or selected by this helper]
    # }
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
