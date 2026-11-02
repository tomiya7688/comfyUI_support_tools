from pathlib import Path
import sys
import unittest

MODULE_DIR = Path(__file__).parents[3] / "tools" / "completion"
sys.path.insert(0, str(MODULE_DIR))

import pr_safety  # noqa: E402


REPO = pr_safety.DEFAULT_REPOSITORY


# {
#   責務: [pr_payload: builds a pull-request API payload with the specified state and mergeability]
#   処理: [1: create required pull request fields, 2: apply the selected state and mergeability values]
#   引数: [**overrides: **overrides passed to this helper (unspecified)]
#   戻り値: [result: payload value built or selected by this helper]
# }
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


# {
#   責務: [PrSafetyTests: related test fixtures and cases for PrSafety behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class PrSafetyTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_clean_feature_branch_is_allowed: verifies the behavior described by "clean feature branch is allowed",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for clean feature branch is allowed,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [test_main_branch_is_blocked: verifies the behavior described by "main branch is blocked"]
    #   処理: [
    #     1: arrange case data and fixture state for main branch is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [
    #     test_unknown_mergeability_is_blocked: verifies the behavior described by "unknown mergeability is blocked",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for unknown mergeability is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [test_failed_status_is_blocked: verifies the behavior described by "failed status is blocked"]
    #   処理: [
    #     1: arrange case data and fixture state for failed status is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [
    #     test_incomplete_check_run_is_blocked: verifies the behavior described by "incomplete check run is blocked",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for incomplete check run is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [test_failed_check_run_is_blocked: verifies the behavior described by "failed check run is blocked"]
    #   処理: [
    #     1: arrange case data and fixture state for failed check run is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [test_wrong_repository_is_blocked: verifies the behavior described by "wrong repository is blocked"]
    #   処理: [
    #     1: arrange case data and fixture state for wrong repository is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [test_wrong_base_is_blocked: verifies the behavior described by "wrong base is blocked"]
    #   処理: [
    #     1: arrange case data and fixture state for wrong base is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [test_branch_mismatch_is_blocked: verifies the behavior described by "branch mismatch is blocked"]
    #   処理: [
    #     1: arrange case data and fixture state for branch mismatch is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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

    # {
    #   責務: [test_unexpected_diff_is_blocked: verifies the behavior described by "unexpected diff is blocked"]
    #   処理: [
    #     1: arrange case data and fixture state for unexpected diff is blocked,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
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
