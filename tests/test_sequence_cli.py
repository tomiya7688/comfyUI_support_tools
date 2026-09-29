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


class SequenceCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store = SequenceStore(self.directory)

    def test_list_returns_saved_definition_names_as_json(self) -> None:
        self.store.save(SequenceDefinition("sample-sequence", (SequenceStep("one", "echo"),)))
        output = io.StringIO()

        status = main(["--directory", str(self.directory), "list"], stdout=output)

        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue()), {"sequences": ["sample-sequence"]})

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
