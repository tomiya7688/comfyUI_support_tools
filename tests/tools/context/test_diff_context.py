from pathlib import Path
import sys
import unittest
from unittest.mock import patch

MODULE_DIR = Path(__file__).parents[3] / "tools" / "context"
sys.path.insert(0, str(MODULE_DIR))

import diff_context  # noqa: E402


# {
#   責務: [DiffContextTests: related test fixtures and cases for DiffContext behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class DiffContextTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_collects_files_symbols_and_bounded_patch: verifies the behavior described by "collects files symbols and bounded patch",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for collects files symbols and bounded patch,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: [run_git: run git passed to this helper (unspecified)]
    #   戻り値: [None: test helper returns no value]
    # }
    @patch("diff_context._run_git")
    def test_collects_files_symbols_and_bounded_patch(self, run_git):
        run_git.side_effect = [
            "a.py\nb.txt\n",
            "diff --git a/a.py b/a.py\n@@ -1,0 +2,2 @@ def hello():\n+def hello():\n+    return 1\n",
        ]
        result = diff_context.collect_diff_context("main", 2)
        self.assertEqual(result.changed_files, ["a.py", "b.txt"])
        self.assertEqual(result.changed_symbols, ["hello"])
        self.assertEqual(len(result.patch_lines), 2)

    # {
    #   責務: [
    #     test_git_failure_returns_empty_context: verifies the behavior described by "git failure returns empty context",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for git failure returns empty context,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: [_run_git:  run git passed to this helper (unspecified)]
    #   戻り値: [None: test helper returns no value]
    # }
    @patch("diff_context._run_git", side_effect=OSError("git missing"))
    def test_git_failure_returns_empty_context(self, _run_git):
        self.assertEqual(
            diff_context.collect_diff_context(),
            diff_context.DiffContext([], [], []),
        )


if __name__ == "__main__":
    unittest.main()
