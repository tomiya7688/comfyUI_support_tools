from pathlib import Path
import sys
import unittest
from unittest.mock import patch

MODULE_DIR = Path(__file__).parents[3] / "tools" / "context"
sys.path.insert(0, str(MODULE_DIR))

import diff_context  # noqa: E402


class DiffContextTests(unittest.TestCase):
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

    @patch("diff_context._run_git", side_effect=OSError("git missing"))
    def test_git_failure_returns_empty_context(self, _run_git):
        self.assertEqual(
            diff_context.collect_diff_context(),
            diff_context.DiffContext([], [], []),
        )


if __name__ == "__main__":
    unittest.main()
