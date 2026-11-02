from pathlib import Path
import sys
import unittest
from unittest import mock

MODULE_DIR = Path(__file__).parents[3] / "tools" / "completion"
sys.path.insert(0, str(MODULE_DIR))

import completion_gate  # noqa: E402


# {
#   責務: [CompletionGateTests: related test fixtures and cases for CompletionGate behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class CompletionGateTests(unittest.TestCase):
    # {
    #   責務: [test_comment_coverage_checks_migrated_source_areas: strict coverage対象にsharedとentrypointsが含まれることを検証する]
    #   処理: [comment_coverage_checkから起動するcommand argumentsを捕捉し、全移行済みprefixとstrict flagを確認する]
    #   引数: []
    #   戻り値: [なし]
    # }
    def test_comment_coverage_checks_migrated_source_areas(self):
        with mock.patch.object(completion_gate, "run") as run:
            completion_gate.comment_coverage_check()
        command = run.call_args.args[0]
        paths = [command[index + 1] for index, value in enumerate(command) if value == "--path"]
        self.assertEqual(
            paths,
            [
                "tools",
                "tests",
                "src/comfyui_support_tools/shared",
                "src/comfyui_support_tools/entrypoints",
                "src/comfyui_support_tools/applications/sequence",
            ],
        )
        self.assertIn("--strict", command)

    # {
    #   責務: [test_stops_on_failed_check: verifies the behavior described by "stops on failed check"]
    #   処理: [
    #     1: arrange case data and fixture state for stops on failed check,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_stops_on_failed_check(self):
        with (
            mock.patch.object(
                completion_gate,
                "compile_check",
                return_value=completion_gate.CheckResult("compile", 1),
            ),
            mock.patch.object(completion_gate, "quality_check") as quality,
            mock.patch.object(completion_gate, "comment_coverage_check") as coverage,
            mock.patch.object(completion_gate, "test_check") as tests,
            mock.patch.object(completion_gate, "generated_docs_check") as docs,
            mock.patch.object(completion_gate, "architecture_check") as architecture,
            mock.patch.object(completion_gate, "upd_architecture_check") as upd,
            mock.patch.object(completion_gate, "diff_check") as diff,
        ):
            self.assertEqual(completion_gate.main([]), 1)
            quality.assert_not_called()
            coverage.assert_not_called()
            tests.assert_not_called()
            docs.assert_not_called()
            architecture.assert_not_called()
            upd.assert_not_called()
            diff.assert_not_called()

    # {
    #   責務: [
    #     test_skip_tests_still_runs_docs_architecture_and_diff: verifies the behavior described by "skip tests still runs docs architecture and diff",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for skip tests still runs docs architecture and diff,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_skip_tests_still_runs_docs_architecture_and_diff(self):
        with (
            mock.patch.object(
                completion_gate,
                "compile_check",
                return_value=completion_gate.CheckResult("compile", 0),
            ),
            mock.patch.object(
                completion_gate,
                "quality_check",
                return_value=completion_gate.CheckResult("quality", 0),
            ) as quality,
            mock.patch.object(
                completion_gate,
                "comment_coverage_check",
                return_value=completion_gate.CheckResult("coverage", 0),
            ) as coverage,
            mock.patch.object(completion_gate, "test_check") as tests,
            mock.patch.object(
                completion_gate,
                "generated_docs_check",
                return_value=completion_gate.CheckResult("docs", 0),
            ) as docs,
            mock.patch.object(
                completion_gate,
                "architecture_check",
                return_value=completion_gate.CheckResult("architecture", 0),
            ) as architecture,
            mock.patch.object(
                completion_gate,
                "upd_architecture_check",
                return_value=completion_gate.CheckResult("upd", 0),
            ) as upd,
            mock.patch.object(
                completion_gate, "diff_check", return_value=completion_gate.CheckResult("diff", 0)
            ) as diff,
        ):
            self.assertEqual(completion_gate.main(["--skip-tests"]), 0)
            quality.assert_called_once()
            coverage.assert_called_once()
            tests.assert_not_called()
            docs.assert_called_once()
            architecture.assert_called_once()
            upd.assert_called_once()
            diff.assert_called_once()

    # {
    #   責務: [
    #     test_stops_when_generated_docs_are_stale: verifies the behavior described by "stops when generated docs are stale",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for stops when generated docs are stale,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_stops_when_generated_docs_are_stale(self):
        with (
            mock.patch.object(
                completion_gate,
                "compile_check",
                return_value=completion_gate.CheckResult("compile", 0),
            ),
            mock.patch.object(
                completion_gate,
                "quality_check",
                return_value=completion_gate.CheckResult("quality", 0),
            ),
            mock.patch.object(
                completion_gate,
                "comment_coverage_check",
                return_value=completion_gate.CheckResult("coverage", 0),
            ),
            mock.patch.object(
                completion_gate, "test_check", return_value=completion_gate.CheckResult("tests", 0)
            ),
            mock.patch.object(
                completion_gate,
                "generated_docs_check",
                return_value=completion_gate.CheckResult("docs", 1),
            ),
            mock.patch.object(completion_gate, "architecture_check") as architecture,
            mock.patch.object(completion_gate, "upd_architecture_check") as upd,
            mock.patch.object(completion_gate, "diff_check") as diff,
        ):
            self.assertEqual(completion_gate.main([]), 1)
            architecture.assert_not_called()
            upd.assert_not_called()
            diff.assert_not_called()

    # {
    #   責務: [
    #     test_stops_on_architecture_violation: verifies the behavior described by "stops on architecture violation",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for stops on architecture violation,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_stops_on_architecture_violation(self):
        with (
            mock.patch.object(
                completion_gate,
                "compile_check",
                return_value=completion_gate.CheckResult("compile", 0),
            ),
            mock.patch.object(
                completion_gate,
                "quality_check",
                return_value=completion_gate.CheckResult("quality", 0),
            ),
            mock.patch.object(
                completion_gate,
                "comment_coverage_check",
                return_value=completion_gate.CheckResult("coverage", 0),
            ),
            mock.patch.object(
                completion_gate, "test_check", return_value=completion_gate.CheckResult("tests", 0)
            ),
            mock.patch.object(
                completion_gate,
                "generated_docs_check",
                return_value=completion_gate.CheckResult("docs", 0),
            ),
            mock.patch.object(
                completion_gate,
                "architecture_check",
                return_value=completion_gate.CheckResult("architecture", 1),
            ),
            mock.patch.object(completion_gate, "upd_architecture_check") as upd,
            mock.patch.object(completion_gate, "diff_check") as diff,
        ):
            self.assertEqual(completion_gate.main([]), 1)
            upd.assert_not_called()
            diff.assert_not_called()

    # {
    #   責務: [
    #     test_stops_on_upd_architecture_violation: verifies the behavior described by "stops on upd architecture violation",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for stops on upd architecture violation,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_stops_on_upd_architecture_violation(self):
        with (
            mock.patch.object(
                completion_gate,
                "compile_check",
                return_value=completion_gate.CheckResult("compile", 0),
            ),
            mock.patch.object(
                completion_gate,
                "quality_check",
                return_value=completion_gate.CheckResult("quality", 0),
            ),
            mock.patch.object(
                completion_gate,
                "comment_coverage_check",
                return_value=completion_gate.CheckResult("coverage", 0),
            ),
            mock.patch.object(
                completion_gate, "test_check", return_value=completion_gate.CheckResult("tests", 0)
            ),
            mock.patch.object(
                completion_gate,
                "generated_docs_check",
                return_value=completion_gate.CheckResult("docs", 0),
            ),
            mock.patch.object(
                completion_gate,
                "architecture_check",
                return_value=completion_gate.CheckResult("architecture", 0),
            ),
            mock.patch.object(
                completion_gate,
                "upd_architecture_check",
                return_value=completion_gate.CheckResult("upd", 1),
            ),
            mock.patch.object(completion_gate, "diff_check") as diff,
        ):
            self.assertEqual(completion_gate.main([]), 1)
            diff.assert_not_called()


if __name__ == "__main__":
    unittest.main()
