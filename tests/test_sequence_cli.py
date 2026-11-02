from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest

from comfyui_support_tools.applications.sequence.data.processing.sequence_store import SequenceStore
from comfyui_support_tools.applications.sequence.process.processing.sequence_runner import SequenceRunner
from comfyui_support_tools.entrypoints.sequence_cli import main
from comfyui_support_tools.shared.contracts.sequence_contracts import SequenceDefinition, SequenceStep


# {
#   責務: [SequenceCliTests: related test fixtures and cases for SequenceCli behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [
#     temp: temporary root containing fixture files,
#     directory: directory fixture state used by the test cases,
#     store: store fixture state used by the test cases,
#   ],
#   引数: []
# }
class SequenceCliTests(unittest.TestCase):
    # {
    #   責務: [setUp: initializes per-test fixture state for SequenceCliTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = SequenceStore(self.directory)

    # {
    #   責務: [
    #     test_list_returns_saved_definition_names_as_json: verifies the behavior described by "list returns saved definition names as json",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for list returns saved definition names as json,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_list_returns_saved_definition_names_as_json(self) -> None:
        self.store.save(SequenceDefinition("sample-sequence", (SequenceStep("one", "echo"),)))
        output = io.StringIO()

        status = main(["--directory", str(self.directory), "list"], stdout=output)

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue()), {"sequences": ["sample-sequence"]})

    # {
    #   責務: [
    #     test_run_executes_saved_definition_and_reports_step_data: verifies the behavior described by "run executes saved definition and reports step data",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for run executes saved definition and reports step data,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_run_executes_saved_definition_and_reports_step_data(self) -> None:
        definition = SequenceDefinition(
            "saved-sequence",
            (SequenceStep("one", "echo", {"message": "hello"}),),
        )
        self.store.save(definition)
        output = io.StringIO()
        runner = SequenceRunner({"echo": lambda inputs, _context: {"answer": inputs["message"]}})

        status = main(
            ["--directory", str(self.directory), "run", "saved-sequence"],
            stdout=output,
            runner=runner,
        )

        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["state"], "done")
        self.assertEqual(result["steps"][0]["inputs"], {"message": "hello"})
        self.assertEqual(result["steps"][0]["outputs"], {"answer": "hello"})

    # {
    #   責務: [
    #     test_failed_step_returns_nonzero_and_error_details: verifies the behavior described by "failed step returns nonzero and error details",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for failed step returns nonzero and error details,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_failed_step_returns_nonzero_and_error_details(self) -> None:
        self.store.save(SequenceDefinition("broken", (SequenceStep("one", "broken"),)))
        output = io.StringIO()
        runner = SequenceRunner({
            "broken": lambda _inputs, _context: (_ for _ in ()).throw(RuntimeError("failed")),
        })

        status = main(
            ["--directory", str(self.directory), "run", "broken"],
            stdout=output,
            runner=runner,
        )

        self.assertEqual(status, 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["steps"][0]["state"], "error")
        self.assertEqual(result["steps"][0]["error"], "RuntimeError: failed")

    # {
    #   責務: [
    #     test_missing_definition_is_reported_as_cli_error: verifies the behavior described by "missing definition is reported as cli error",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for missing definition is reported as cli error,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_missing_definition_is_reported_as_cli_error(self) -> None:
        output = io.StringIO()
        errors = io.StringIO()

        status = main(
            ["--directory", str(self.directory), "run", "missing"],
            stdout=output,
            stderr=errors,
            runner=SequenceRunner({}),
        )

        self.assertEqual(status, 2)
        self.assertEqual(json.loads(errors.getvalue())["state"], "error")


    # {
    #   責務: [
    #     test_save_imports_definition_file_into_configured_directory: verifies the behavior described by "save imports definition file into configured directory",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for save imports definition file into configured directory,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_save_imports_definition_file_into_configured_directory(self) -> None:
        source_directory = self.directory / "imported"
        definition = SequenceDefinition(
            "portable-sequence",
            (SequenceStep("one", "echo", {"value": "saved"}),),
        )
        source_path = SequenceStore(source_directory).save(definition)
        output = io.StringIO()

        status = main(
            ["--directory", str(self.directory), "save", str(source_path)],
            stdout=output,
        )

        self.assertEqual(status, 0)
        self.assertEqual(SequenceStore(self.directory).load(definition.name), definition)
        self.assertEqual(json.loads(output.getvalue())["state"], "saved")

    # {
    #   責務: [
    #     test_save_does_not_replace_existing_definition_without_overwrite_flag: verifies the behavior described by "save does not replace existing definition without overwrite flag",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for save does not replace existing definition without overwrite flag,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_save_does_not_replace_existing_definition_without_overwrite_flag(self) -> None:
        existing = SequenceDefinition(
            "same-name",
            (SequenceStep("one", "echo", {"value": "keep"}),),
        )
        replacement = SequenceDefinition(
            "same-name",
            (SequenceStep("one", "echo", {"value": "replace"}),),
        )
        self.store.save(existing)
        source_path = SequenceStore(self.directory / "imported").save(replacement)
        errors = io.StringIO()

        status = main(
            ["--directory", str(self.directory), "save", str(source_path)],
            stderr=errors,
        )

        self.assertEqual(status, 2)
        self.assertEqual(SequenceStore(self.directory).load("same-name"), existing)
        self.assertIn("--overwrite", errors.getvalue())
if __name__ == "__main__":
    unittest.main()
