from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from comfyui_support_tools.applications.sequence.data.processing.sequence_store import (
    SequenceStore,
)
from comfyui_support_tools.applications.sequence.process.processing.sequence_runner import (
    SequenceRunner,
)
from comfyui_support_tools.shared.contracts.sequence_contracts import (
    FailurePolicy,
    SequenceDefinition,
    SequenceStep,
)


class SequenceRunnerTests(unittest.TestCase):
    def test_commands_run_in_order_and_share_explicit_outputs(self) -> None:
        observed: list[str] = []

        def generate(inputs, _context):
            observed.append("generate")
            return {"image": f"{inputs['prompt']}.png"}

        def tag(inputs, _context):
            observed.append("tag")
            return {"tags": f"tags for {inputs['image']}"}

        def caption(inputs, _context):
            observed.append("caption")
            return {"caption": f"caption for {inputs['tags']}"}

        definition = SequenceDefinition(
            "three-commands",
            (
                SequenceStep("generate", "generate", {"prompt": "portrait"}),
                SequenceStep("tag", "tag", {"image": {"$ref": "context.generate.image"}}),
                SequenceStep("caption", "caption", {"tags": {"$ref": "context.tag.tags"}}),
            ),
        )

        result = SequenceRunner(
            {"generate": generate, "tag": tag, "caption": caption}
        ).run(definition)

        self.assertEqual(observed, ["generate", "tag", "caption"])
        self.assertEqual(result.state, "done")
        self.assertEqual([step.state for step in result.steps], ["done"] * 3)
        self.assertEqual(result.context["caption"]["caption"], "caption for tags for portrait.png")

    def test_stop_policy_records_failed_and_skipped_steps(self) -> None:
        definition = SequenceDefinition(
            "stop-on-error",
            (
                SequenceStep("bad", "bad"),
                SequenceStep("later", "ok"),
            ),
        )
        result = SequenceRunner({"bad": lambda _i, _c: (_ for _ in ()).throw(RuntimeError("boom")),
                                 "ok": lambda _i, _c: {}}).run(definition)

        self.assertEqual(result.state, "error")
        self.assertEqual([step.state for step in result.steps], ["error", "skipped"])
        self.assertEqual(result.steps[0].error, "RuntimeError: boom")

    def test_continue_policy_runs_later_steps_after_failure(self) -> None:
        definition = SequenceDefinition(
            "continue-on-error",
            (SequenceStep("bad", "bad"), SequenceStep("later", "ok")),
            FailurePolicy.CONTINUE,
        )
        result = SequenceRunner(
            {"bad": lambda _i, _c: 1, "ok": lambda _i, _c: {"done": True}}
        ).run(definition)

        self.assertEqual([step.state for step in result.steps], ["error", "done"])
        self.assertEqual(result.state, "error")

    def test_missing_context_reference_is_a_step_error(self) -> None:
        definition = SequenceDefinition(
            "missing-reference",
            (SequenceStep("use", "echo", {"value": {"$ref": "context.absent.value"}}),),
        )
        result = SequenceRunner({"echo": lambda inputs, _context: inputs}).run(definition)
        self.assertEqual(result.steps[0].state, "error")
        self.assertIn("context reference not found", result.steps[0].error)

    def test_definitions_require_unique_step_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            SequenceDefinition(
                "duplicate",
                (SequenceStep("same", "noop"), SequenceStep("same", "noop")),
            )


class SequenceStoreTests(unittest.TestCase):
    def test_round_trips_versioned_json_sequence(self) -> None:
        definition = SequenceDefinition(
            "日本語 sequence",
            (SequenceStep("step-1", "echo", {"text": "hello"}),),
            FailurePolicy.CONTINUE,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = SequenceStore(Path(directory))
            saved = store.save(definition)
            loaded = store.load(definition.name)

        self.assertEqual(saved.suffix, ".json")
        self.assertEqual(loaded, definition)

    def test_rejects_invalid_sequence_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SequenceStore(directory)
            (store._directory / "broken.json").write_text('{"steps":{}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "array"):
                store.load("broken")


if __name__ == "__main__":
    unittest.main()
