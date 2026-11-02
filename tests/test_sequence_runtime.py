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


# {
#   責務: [SequenceRunnerTests: related test fixtures and cases for SequenceRunner behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SequenceRunnerTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_commands_run_in_order_and_share_explicit_outputs: verifies the behavior described by "commands run in order and share explicit outputs",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for commands run in order and share explicit outputs,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_commands_run_in_order_and_share_explicit_outputs(self) -> None:
        observed: list[str] = []

        # {
        #   責務: [generate: returns a deterministic image payload for the supplied generation request]
        #   処理: [
        #     1: record or derive the generation output from the supplied sequence inputs,
        #     2: return the deterministic output payload,
        #   ],
        #   引数: [
        #     inputs: input mapping from the previous workflow step (unspecified),
        #     _context: execution context passed through the workflow (unspecified),
        #   ],
        #   戻り値: [result: mapping built or selected by this helper]
        # }
        def generate(inputs, _context):
            observed.append("generate")
            return {"image": f"{inputs['prompt']}.png"}

        # {
        #   責務: [tag: returns the canned tag response used by the backend test double]
        #   処理: [
        #     1: record or derive tag output from the supplied sequence inputs,
        #     2: return the deterministic tag payload,
        #   ],
        #   引数: [
        #     inputs: input mapping from the previous workflow step (unspecified),
        #     _context: execution context passed through the workflow (unspecified),
        #   ],
        #   戻り値: [result: mapping built or selected by this helper]
        # }
        def tag(inputs, _context):
            observed.append("tag")
            return {"tags": f"tags for {inputs['image']}"}

        # {
        #   責務: [caption: records the prompt passed to the caption step and returns deterministic caption output]
        #   処理: [1: record the prompt and derive a stable caption result, 2: return the deterministic caption payload]
        #   引数: [
        #     inputs: input mapping from the previous workflow step (unspecified),
        #     _context: execution context passed through the workflow (unspecified),
        #   ],
        #   戻り値: [result: mapping built or selected by this helper]
        # }
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

    # {
    #   責務: [
    #     test_stop_policy_records_failed_and_skipped_steps: verifies the behavior described by "stop policy records failed and skipped steps",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for stop policy records failed and skipped steps,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
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

    # {
    #   責務: [
    #     test_continue_policy_runs_later_steps_after_failure: verifies the behavior described by "continue policy runs later steps after failure",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for continue policy runs later steps after failure,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
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

    # {
    #   責務: [
    #     test_missing_context_reference_is_a_step_error: verifies the behavior described by "missing context reference is a step error",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for missing context reference is a step error,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_missing_context_reference_is_a_step_error(self) -> None:
        definition = SequenceDefinition(
            "missing-reference",
            (SequenceStep("use", "echo", {"value": {"$ref": "context.absent.value"}}),),
        )
        result = SequenceRunner({"echo": lambda inputs, _context: inputs}).run(definition)
        self.assertEqual(result.steps[0].state, "error")
        self.assertIn("context reference not found", result.steps[0].error)

    # {
    #   責務: [
    #     test_definitions_require_unique_step_ids: verifies the behavior described by "definitions require unique step ids",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for definitions require unique step ids,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    # }
    def test_definitions_require_unique_step_ids(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            SequenceDefinition(
                "duplicate",
                (SequenceStep("same", "noop"), SequenceStep("same", "noop")),
            )


# {
#   責務: [SequenceStoreTests: related test fixtures and cases for SequenceStore behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class SequenceStoreTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_round_trips_versioned_json_sequence: verifies the behavior described by "round trips versioned json sequence",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for round trips versioned json sequence,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
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

    # {
    #   責務: [test_rejects_invalid_sequence_json: verifies the behavior described by "rejects invalid sequence json"]
    #   処理: [
    #     1: arrange case data and fixture state for rejects invalid sequence json,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [result: None produced for the supplied fixture/input]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_rejects_invalid_sequence_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SequenceStore(directory)
            (store._directory / "broken.json").write_text('{"steps":{}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "array"):
                store.load("broken")


if __name__ == "__main__":
    unittest.main()
