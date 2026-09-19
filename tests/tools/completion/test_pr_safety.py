from pathlib import Path
import sys
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "completion"
sys.path.insert(0, str(MODULE_DIR))

import pr_safety  # noqa: E402


REPO = pr_safety.DEFAULT_REPOSITORY


def pr_payload(**overrides):
    payload = {
        "state": "open",
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "base": {"ref": "main", "repo": {"full_name": REPO}},
        "head": {"ref": "feature/example", "repo": {"full_name": REPO}},
    }
    payload.update(overrides)
    return payload


class PrSafetyTests(unittest.TestCase):
    def test_clean_feature_branch_is_allowed(self):
        result = pr_safety.evaluate(
            "feature/example",
            pr_payload(),
            {"state": "success"},
            {"check_runs": [{"name": "build", "status": "completed", "conclusion": "success"}]},
            ["tools/completion/pr_safety.py"],
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.reasons, ())

    def test_main_branch_is_blocked(self):
        result = pr_safety.evaluate(
            "main",
            pr_payload(head={"ref": "main", "repo": {"full_name": REPO}}),
            {"state": "success"},
            {"check_runs": []},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("default branch" in reason for reason in result.reasons))

    def test_unknown_mergeability_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            pr_payload(mergeable=None, mergeable_state="unknown"),
            {"state": "pending"},
            {"check_runs": []},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("unknown" in reason for reason in result.reasons))

    def test_failed_status_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            pr_payload(),
            {"state": "failure"},
            {"check_runs": []},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("failure" in reason for reason in result.reasons))

    def test_incomplete_check_run_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            pr_payload(),
            {"state": "success"},
            {"check_runs": [{"name": "build", "status": "in_progress", "conclusion": None}]},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("not complete" in reason for reason in result.reasons))

    def test_failed_check_run_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            pr_payload(),
            {"state": "success"},
            {"check_runs": [{"name": "build", "status": "completed", "conclusion": "failure"}]},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("did not pass" in reason for reason in result.reasons))

    def test_wrong_repository_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            pr_payload(head={"ref": "feature/example", "repo": {"full_name": "tomiya7688/other-project"}}),
            {"state": "success"},
            {"check_runs": []},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("head repository" in reason for reason in result.reasons))

    def test_wrong_base_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            pr_payload(base={"ref": "develop", "repo": {"full_name": REPO}}),
            {"state": "success"},
            {"check_runs": []},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("expected main" in reason for reason in result.reasons))

    def test_branch_mismatch_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/other",
            pr_payload(),
            {"state": "success"},
            {"check_runs": []},
            [],
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("does not match PR head" in reason for reason in result.reasons))

    def test_unexpected_diff_is_blocked(self):
        result = pr_safety.evaluate(
            "feature/example",
            pr_payload(),
            {"state": "success"},
            {"check_runs": []},
            ["tools/completion/pr_safety.py", "tabbed_tools_gui.py"],
            ("tools/", "tests/"),
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("tabbed_tools_gui.py" in reason for reason in result.reasons))


if __name__ == "__main__":
    unittest.main()
