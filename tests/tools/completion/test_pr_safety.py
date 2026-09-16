from pathlib import Path
import sys
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "completion"
sys.path.insert(0, str(MODULE_DIR))

import pr_safety  # noqa: E402


class PrSafetyTests(unittest.TestCase):
    def test_clean_feature_branch_is_allowed(self):
        result = pr_safety.evaluate(
            "feature/example",
            {"draft": False, "mergeable": True, "mergeable_state": "clean"},
            {"state": "success"},
            ["tools/completion/pr_safety.py"],
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.reasons, ())

    def test_main_branch_is_blocked(self):
        result = pr_safety.evaluate(
            "main",
            {"draft": False, "mergeable": True, "mergeable_state": "clean"},
            {"state": "success"},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("default branch" in reason for reason in result.reasons))

    def test_unknown_mergeability_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            {"draft": False, "mergeable": None, "mergeable_state": "unknown"},
            {"state": "pending"},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("unknown" in reason for reason in result.reasons))

    def test_failed_status_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            {"draft": False, "mergeable": True, "mergeable_state": "clean"},
            {"state": "failure"},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("failure" in reason for reason in result.reasons))

    def test_unexpected_diff_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            {"draft": False, "mergeable": True, "mergeable_state": "clean"},
            {"state": "success"},
            ["tools/completion/pr_safety.py", "tabbed_tools_gui.py"],
            ("tools/", "tests/"),
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("tabbed_tools_gui.py" in reason for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
