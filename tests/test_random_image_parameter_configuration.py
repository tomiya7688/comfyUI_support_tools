import unittest
from types import SimpleNamespace

from scripts.tabs.random_image import RandomImageTab


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class RandomImageParameterConfigurationTests(unittest.TestCase):
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

    def test_fixed_choices_continue_to_use_existing_controls(self):
        tab = self._tab()
        self.assertEqual(RandomImageTab._generation_parameter_config(tab), {
            "cfg": {"mode": "fixed", "value": 7.0},
            "steps": {"mode": "fixed", "value": 25},
            "resolution": {"mode": "fixed", "value": {"width": 960, "height": 1280}},
            "sampler": {"mode": "fixed", "value": "Euler a"},
        })

    def test_rejects_malformed_range_and_resolution_candidate(self):
        tab = self._tab(cfg="7..8..9")
        with self.assertRaisesRegex(ValueError, "CFGの範囲"):
            RandomImageTab._generation_parameter_config(tab)
        tab = self._tab(resolution_mode="candidate", resolution_candidates="512 by 768")
        with self.assertRaisesRegex(ValueError, "解像度候補の形式"):
            RandomImageTab._generation_parameter_config(tab)

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
