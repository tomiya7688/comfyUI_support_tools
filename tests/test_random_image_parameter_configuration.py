import unittest
from types import SimpleNamespace

from scripts.tabs.random_image import RandomImageTab


# {
#   責務: [_Value: reusable fixture or controlled test double for _Value behavior]
#   処理: [1: provide the configured fields and methods used by the surrounding cases]
#   フィールド: [value: value fixture state used by the test cases]
#   引数: []
# }
class _Value:
    # {
    #   責務: [__init__: initializes the fields and controlled behavior of _Value]
    #   処理: [1: store constructor inputs and initialize controlled fixture state]
    #   引数: [value: value to serialize or write (unspecified)]
    #   戻り値: [None: initialize instance state without returning a value]
    # }
    def __init__(self, value):
        self.value = value

    # {
    #   責務: [get: records or returns a deterministic HTTP response for the requested endpoint]
    #   処理: [1: record the requested endpoint, 2: select the matching configured payload or error response]
    #   引数: []
    #   戻り値: [result: value returned by the helper's documented test role]
    # }
    def get(self):
        return self.value


# {
#   責務: [
#     RandomImageParameterConfigurationTests: related test fixtures and cases for RandomImageParameterConfiguration behavior,
#   ],
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class RandomImageParameterConfigurationTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_builds_range_and_candidate_specs_from_gui_values: verifies the behavior described by "builds range and candidate specs from gui values",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for builds range and candidate specs from gui values,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_builds_range_and_candidate_specs_from_gui_values(self):
        tab = self._tab(
            cfg="4.5..8.0",
            steps_mode="range",
            steps_range="16..30",
            resolution_mode="candidate",
            resolution_candidates="512x768 | 768x1024",
            sampler_mode="candidate",
            sampler_candidates="Euler a|DPM++ 2M Karras",
        )
        self.assertEqual(RandomImageTab._generation_parameter_config(tab), {
            "cfg": {"mode": "range", "min": 4.5, "max": 8.0},
            "steps": {"mode": "range", "min": 16, "max": 30},
            "resolution": {"mode": "candidate", "values": [
                {"width": 512, "height": 768}, {"width": 768, "height": 1024},
            ]},
            "sampler": {"mode": "candidate", "values": ["Euler a", "DPM++ 2M Karras"]},
        })

    # {
    #   責務: [
    #     test_fixed_choices_continue_to_use_existing_controls: verifies the behavior described by "fixed choices continue to use existing controls",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for fixed choices continue to use existing controls,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_fixed_choices_continue_to_use_existing_controls(self):
        tab = self._tab()
        self.assertEqual(RandomImageTab._generation_parameter_config(tab), {
            "cfg": {"mode": "fixed", "value": 7.0},
            "steps": {"mode": "fixed", "value": 25},
            "resolution": {"mode": "fixed", "value": {"width": 960, "height": 1280}},
            "sampler": {"mode": "fixed", "value": "Euler a"},
        })

    # {
    #   責務: [
    #     test_rejects_malformed_range_and_resolution_candidate: verifies the behavior described by "rejects malformed range and resolution candidate",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for rejects malformed range and resolution candidate,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_rejects_malformed_range_and_resolution_candidate(self):
        tab = self._tab(cfg="7..8..9")
        with self.assertRaisesRegex(ValueError, "CFGの範囲"):
            RandomImageTab._generation_parameter_config(tab)
        tab = self._tab(resolution_mode="candidate", resolution_candidates="512 by 768")
        with self.assertRaisesRegex(ValueError, "解像度候補の形式"):
            RandomImageTab._generation_parameter_config(tab)

    # {
    #   責務: [_tab: builds a tab-like namespace with the supplied generation settings]
    #   処理: [
    #     1: combine setting values in a tab-like namespace,
    #     2: return the namespace consumed by the parser under test,
    #   ],
    #   引数: [
    #     cfg: cfg passed to this helper (unspecified),
    #     steps_mode: steps mode passed to this helper (unspecified),
    #     steps_range: steps range passed to this helper (unspecified),
    #     resolution_mode: resolution mode passed to this helper (unspecified),
    #     resolution_candidates: resolution candidates passed to this helper (unspecified),
    #     sampler_mode: sampler mode passed to this helper (unspecified),
    #     sampler_candidates: sampler candidates passed to this helper (unspecified),
    #   ],
    #   戻り値: [result: SimpleNamespace built or selected by this helper]
    # }
    @staticmethod
    def _tab(
        cfg="7", steps_mode="fixed", steps_range="", resolution_mode="fixed",
        resolution_candidates="", sampler_mode="fixed", sampler_candidates="",
    ):
        return SimpleNamespace(
            var_cfg_spec=_Value(cfg),
            var_steps_mode=_Value(steps_mode),
            var_steps_range=_Value(steps_range),
            var_steps=_Value(25),
            var_resolution_mode=_Value(resolution_mode),
            var_resolution_candidates=_Value(resolution_candidates),
            var_width=_Value(960),
            var_height=_Value(1280),
            var_sampler_mode=_Value(sampler_mode),
            var_sampler_candidates=_Value(sampler_candidates),
            var_sampler_index=_Value("Euler a"),
            _parse_range=RandomImageTab._parse_range,
        )


if __name__ == "__main__":
    unittest.main()
