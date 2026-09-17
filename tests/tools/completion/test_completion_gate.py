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
             mock.patch.object(completion_gate, "generated_docs_check") as docs, \
             mock.patch.object(completion_gate, "architecture_check") as architecture, \
             mock.patch.object(completion_gate, "diff_check") as diff:
            self.assertEqual(completion_gate.main([]), 1)
            tests.assert_not_called()
            docs.assert_not_called()
            architecture.assert_not_called()
            diff.assert_not_called()

    def test_skip_tests_still_runs_docs_architecture_and_diff(self):
        with mock.patch.object(completion_gate, "compile_check", return_value=completion_gate.CheckResult("compile", 0)), \
             mock.patch.object(completion_gate, "test_check") as tests, \
             mock.patch.object(completion_gate, "generated_docs_check", return_value=completion_gate.CheckResult("docs", 0)) as docs, \
             mock.patch.object(completion_gate, "architecture_check", return_value=completion_gate.CheckResult("architecture", 0)) as architecture, \
             mock.patch.object(completion_gate, "diff_check", return_value=completion_gate.CheckResult("diff", 0)) as diff:
            self.assertEqual(completion_gate.main(["--skip-tests"]), 0)
            tests.assert_not_called()
            docs.assert_called_once()
            architecture.assert_called_once()
            diff.assert_called_once()

    def test_stops_when_generated_docs_are_stale(self):
        with mock.patch.object(completion_gate, "compile_check", return_value=completion_gate.CheckResult("compile", 0)), \
             mock.patch.object(completion_gate, "test_check", return_value=completion_gate.CheckResult("tests", 0)), \
             mock.patch.object(completion_gate, "generated_docs_check", return_value=completion_gate.CheckResult("docs", 1)), \
             mock.patch.object(completion_gate, "architecture_check") as architecture, \
             mock.patch.object(completion_gate, "diff_check") as diff:
            self.assertEqual(completion_gate.main([]), 1)
            architecture.assert_not_called()
            diff.assert_not_called()

    def test_stops_on_architecture_violation(self):
        with mock.patch.object(completion_gate, "compile_check", return_value=completion_gate.CheckResult("compile", 0)), \
             mock.patch.object(completion_gate, "test_check", return_value=completion_gate.CheckResult("tests", 0)), \
             mock.patch.object(completion_gate, "generated_docs_check", return_value=completion_gate.CheckResult("docs", 0)), \
             mock.patch.object(completion_gate, "architecture_check", return_value=completion_gate.CheckResult("architecture", 1)), \
             mock.patch.object(completion_gate, "diff_check") as diff:
            self.assertEqual(completion_gate.main([]), 1)
            diff.assert_not_called()


if __name__ == "__main__":
    unittest.main()
