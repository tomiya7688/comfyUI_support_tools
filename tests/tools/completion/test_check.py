from pathlib import Path
import sys
import unittest
from unittest import mock

MODULE_DIR = Path(__file__).parents[3] / "tools" / "completion"
sys.path.insert(0, str(MODULE_DIR))

import check  # noqa: E402


class LocalCheckTests(unittest.TestCase):
    def test_runs_shared_gate_and_reports_no_tests_for_docs_only_change(self):
        with mock.patch.object(check, "_changed_paths", return_value=()), \
             mock.patch.object(check, "_test_modules", return_value=()), \
             mock.patch.object(check.completion_gate, "main", return_value=0) as gate:
            self.assertEqual(check.main(), 0)
        gate.assert_called_once_with(["--skip-tests"])

    def test_propagates_shared_gate_failure(self):
        with mock.patch.object(check, "_changed_paths", return_value=()), \
             mock.patch.object(check.completion_gate, "main", return_value=1):
            self.assertEqual(check.main(), 1)


if __name__ == "__main__":
    unittest.main()
