from pathlib import Path
import sys
import unittest
from unittest import mock

MODULE_DIR = Path(__file__).parents[3] / "tools" / "completion"
sys.path.insert(0, str(MODULE_DIR))

import completion_gate  # noqa: E402


class CompletionGateTests(unittest.TestCase):
    def test_stops_on_failed_check(self):
        with mock.patch.object(completion_gate, "compile_check", return_value=completion_gate.CheckResult("compile", 1)), \
             mock.patch.object(completion_gate, "test_check") as tests, \
             mock.patch.object(completion_gate, "diff_check") as diff:
            self.assertEqual(completion_gate.main([]), 1)
            tests.assert_not_called()
            diff.assert_not_called()

    def test_skip_tests_runs_compile_and_diff(self):
        with mock.patch.object(completion_gate, "compile_check", return_value=completion_gate.CheckResult("compile", 0)), \
             mock.patch.object(completion_gate, "test_check") as tests, \
             mock.patch.object(completion_gate, "diff_check", return_value=completion_gate.CheckResult("diff", 0)):
            self.assertEqual(completion_gate.main(["--skip-tests"]), 0)
            tests.assert_not_called()


if __name__ == "__main__":
    unittest.main()
