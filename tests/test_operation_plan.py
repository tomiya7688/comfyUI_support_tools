"""Shared operation plan, stale detection, preview, and apply tests."""

import argparse
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from comfyui_support_tools.shared.contracts.operation_plan import (
    OperationMode,
    PlanExecutionStatus,
    PlannedAction,
)
from comfyui_support_tools.shared.operation_plan import (
    add_operation_cli_arguments,
    apply_operation_plan,
    create_operation_plan,
    load_operation_plan,
    preview_operation_plan,
    resolve_operation_cli_options,
    save_operation_plan,
)


# {
#   責務: [OperationPlanTests: GUI/CLI共通planの保存、preview、stale guard、applyを検証する]
#   フィールド: [temp source、settings mapping]
# }
class OperationPlanTests(unittest.TestCase):
    # {
    #   責務: [_plan: test用source/settings/actionを共通OperationPlanへ変換する]
    #   処理: [1: PlannedActionを作る 2: shared plan builderへ渡す]
    #   引数: [source: source path, settings: settings, mode: plan mode, actions: optional proposals, conflicts: conflicts]
    #   戻り値: [plan: immutable OperationPlan]
    # }
    def _plan(self, source, settings, *, mode=OperationMode.DRY_RUN, actions=None, conflicts=()):
        proposed = actions or (
            PlannedAction(
                "action-1",
                "source-1",
                "copy",
                "destination/item.bin",
                ("extension:bin", "reviewed:yes"),
            ),
        )
        return create_operation_plan(
            "operation-test",
            mode,
            {"source-1": source},
            proposed,
            settings,
            skipped_count=2,
            warnings=("sample warning",),
            conflicts=conflicts,
            estimated_resources={"bytes": 1024},
            output_destinations=("destination",),
            decision_reasons=("extension:bin",),
            before_count=10,
            after_count=8,
        )

    # {
    #   責務: [test_plan_builder_rejects_malformed_inputs_with_value_error: 不正なbuilder入力を一貫して拒否する]
    #   処理: [1: 各不正入力を与える 2: ValueErrorを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_plan_builder_rejects_malformed_inputs_with_value_error(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_text("x", encoding="utf-8")
            valid_action = PlannedAction("copy", "source-1", "copy")
            cases = (
                {"operation_id": None},
                {"confidence": True},
                {"sources": {1: source}},
                {"actions": (object(),)},
                {"estimated_resources": {"bytes": float("inf")}},
            )
            for overrides in cases:
                arguments = {
                    "operation_id": "operation-test",
                    "mode": OperationMode.DRY_RUN,
                    "sources": {"source-1": source},
                    "actions": (valid_action,),
                    "settings": {},
                }
                arguments.update(overrides)
                with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                    create_operation_plan(**arguments)

    # {
    #   責務: [test_snapshot_rejects_invalid_hash_limits: 不正なhash上限を拒否する]
    #   処理: [1: 負数/真偽値/小数を与える 2: ValueErrorを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_snapshot_rejects_invalid_hash_limits(self):
        from comfyui_support_tools.shared.operation_plan import capture_source_snapshot

        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_text("x", encoding="utf-8")
            for limit in (-1, True, 1.5):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    capture_source_snapshot("source-1", source, limit)

    # {
    #   責務: [test_plan_round_trip_is_atomic_and_digest_checked: plan JSON保存とintegrity digestを検証する]
    #   処理: [1: plan manifestを書き戻す 2: dataclass equalityを確認する 3: tamperを拒否する]
    #   引数: []
    #   戻り値: []
    # }
    def test_plan_round_trip_is_atomic_and_digest_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "item.bin"
            source.write_bytes(b"before")
            plan = self._plan(source, {"mode": "sort", "threshold": 0.8})
            manifest = root / "plan.json"
            self.assertEqual(save_operation_plan(plan, manifest), manifest)
            self.assertEqual(load_operation_plan(manifest), plan)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["plan"]["settings_sha256"] = "0" * 64
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest"):
                load_operation_plan(manifest)
            payload["plan"]["affected_count"] += 1
            canonical = json.dumps(
                payload["plan"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            payload["plan_sha256"] = hashlib.sha256(canonical).hexdigest()
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "affected count"):
                load_operation_plan(manifest)

    # {
    #   責務: [test_preview_prioritizes_high_risk_then_reason_and_seeded_samples: preview sample policyを検証する]
    #   処理: [1: risk/reason別actionsを作る 2: risk優先とreason distributionを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_preview_prioritizes_high_risk_then_reason_and_seeded_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_text("x", encoding="utf-8")
            actions = tuple(
                PlannedAction(
                    f"action-{index}",
                    "source-1",
                    "delete" if index == 0 else "copy",
                    decision_reasons=(("duplicate" if index < 4 else "new"),),
                    risk_level="high" if index == 0 else "normal",
                    review_required=index == 0,
                )
                for index in range(10)
            )
            plan = self._plan(source, {}, actions=actions)
            preview = preview_operation_plan(plan, sample_limit=4, seed=7)
            self.assertEqual(preview.actions[0].action_id, "action-0")
            self.assertEqual(preview.review_count, 1)
            self.assertEqual(preview.before_count, 10)
            self.assertEqual(preview.after_count, 8)
            self.assertEqual(dict(preview.reason_distribution), {"duplicate": 4, "new": 6})
            self.assertEqual(preview, preview_operation_plan(plan, sample_limit=4, seed=7))

    # {
    #   責務: [test_apply_rebuilds_same_decisions_and_checks_confirmation: apply前のdecision一致と高risk確認を検証する]
    #   処理: [1: planをrecomputeする 2: high-riskはconfirmationなしで拒否 3: confirmed後にapplyする]
    #   引数: []
    #   戻り値: []
    # }
    def test_apply_rebuilds_same_decisions_and_checks_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_text("unchanged", encoding="utf-8")
            settings = {"operation": "move", "target": "sorted"}
            action = PlannedAction(
                "high-risk",
                "source-1",
                "delete",
                decision_reasons=("duplicate",),
                risk_level="high",
                review_required=True,
            )
            plan = self._plan(source, settings, actions=(action,))

            # {
            #   責務: [rebuild: apply前に同一settings/actionsでfresh planを再構築する]
            #   処理: [1: shared helperでplanを再構築する]
            #   引数: []
            #   戻り値: [plan: recomputed OperationPlan]
            # }
            def rebuild():
                return self._plan(source, settings, actions=(action,))

            applied = []
            not_confirmed = apply_operation_plan(
                plan,
                settings,
                rebuild,
                lambda item: applied.append(item.action_id),
            )
            self.assertEqual(not_confirmed.status, PlanExecutionStatus.CONFIRMATION_REQUIRED)
            self.assertEqual(applied, [])
            confirmed = apply_operation_plan(
                plan,
                settings,
                rebuild,
                lambda item: applied.append(item.action_id),
                confirmed=True,
            )
            self.assertEqual(confirmed.status, PlanExecutionStatus.APPLIED)
            self.assertEqual(applied, ["high-risk"])

    # {
    #   責務: [test_destructive_operation_requires_confirmation: destructive moveを明示確認なしで実行しない]
    #   処理: [1: normal riskのmove planを作る 2: confirmationなしのapplyがblockされることを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_destructive_operation_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_text("data", encoding="utf-8")
            settings = {"operation": "sort"}
            action = PlannedAction("move", "source-1", "move", "sorted/source")
            plan = self._plan(source, settings, actions=(action,))
            apply_action = Mock()
            result = apply_operation_plan(
                plan,
                settings,
                lambda: self._plan(source, settings, actions=(action,)),
                apply_action,
            )
            self.assertEqual(result.status, PlanExecutionStatus.CONFIRMATION_REQUIRED)
            apply_action.assert_not_called()

    # {
    #   責務: [test_stale_source_settings_decisions_and_conflicts_block_apply: apply前stale/conflict conditionsを拒否する]
    #   処理: [1: sourceを変更する 2: settings/action/conflict変更を作る 3: mutation callback未実行を確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_stale_source_settings_decisions_and_conflicts_block_apply(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_bytes(b"old")
            settings = {"sort": "name"}
            plan = self._plan(source, settings)
            apply_callback = Mock()
            source.write_bytes(b"new content")
            result = apply_operation_plan(
                plan,
                settings,
                lambda: self._plan(source, settings),
                apply_callback,
            )
            self.assertEqual(result.status, PlanExecutionStatus.STALE_SOURCE)
            apply_callback.assert_not_called()

            source.write_bytes(b"old")
            stale_settings = apply_operation_plan(
                plan,
                {"sort": "size"},
                lambda: self._plan(source, {"sort": "size"}),
                apply_callback,
            )
            self.assertEqual(stale_settings.status, PlanExecutionStatus.STALE_SETTINGS)

            plan = self._plan(source, settings)
            stale_decisions = apply_operation_plan(
                plan,
                settings,
                lambda: self._plan(
                    source,
                    settings,
                    actions=(PlannedAction("changed", "source-1", "copy"),),
                ),
                apply_callback,
            )
            self.assertEqual(stale_decisions.status, PlanExecutionStatus.STALE_DECISIONS)

            conflicted = self._plan(source, settings, conflicts=("destination exists",))
            blocked = apply_operation_plan(
                conflicted,
                settings,
                lambda: conflicted,
                apply_callback,
            )
            self.assertEqual(blocked.status, PlanExecutionStatus.BLOCKED_CONFLICT)
            apply_callback.assert_not_called()

    # {
    #   責務: [test_apply_failure_rolls_back_completed_reversible_actions: reversible planでpartial applyをrollbackする]
    #   処理: [1: 2 action planを作る 2: 2件目で失敗させる 3: 1件目のrollbackを確認する]
    #   引数: []
    #   戻り値: []
    # }
    def test_apply_failure_rolls_back_completed_reversible_actions(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_text("data", encoding="utf-8")
            actions = (
                PlannedAction("one", "source-1", "copy"),
                PlannedAction("two", "source-1", "copy"),
            )
            settings = {"copy": True}
            plan = self._plan(source, settings, actions=actions)
            apply_action = Mock(side_effect=[None, RuntimeError("write failed")])
            rollback_action = Mock()
            result = apply_operation_plan(
                plan,
                settings,
                lambda: self._plan(source, settings, actions=actions),
                apply_action,
                rollback_action=rollback_action,
            )
            self.assertEqual(result.status, PlanExecutionStatus.FAILED)
            self.assertEqual(result.applied_count, 1)
            self.assertIn("rolled back", result.message)
            rollback_action.assert_called_once_with(actions[0])

    # {
    #   責務: [test_cli_flags_resolve_to_shared_modes: common dry-run/apply plan CLI flagsを検証する]
    #   処理: [1: shared argsを登録する 2: dry-run/apply-plan/manifest-only modeをparseする]
    #   引数: []
    #   戻り値: []
    # }
    def test_cli_flags_resolve_to_shared_modes(self):
        parser = argparse.ArgumentParser()
        add_operation_cli_arguments(parser)
        dry_run = resolve_operation_cli_options(
            parser.parse_args(["--dry-run", "--plan-out", "plan.json"])
        )
        self.assertEqual(dry_run.mode, OperationMode.DRY_RUN)
        self.assertEqual(dry_run.plan_out, Path("plan.json"))
        apply_plan = resolve_operation_cli_options(parser.parse_args(["--apply-plan", "plan.json"]))
        self.assertEqual(apply_plan.mode, OperationMode.APPLY_WITH_REVIEW)
        self.assertEqual(apply_plan.apply_plan, Path("plan.json"))
        manifest = resolve_operation_cli_options(parser.parse_args(["--manifest-only"]))
        self.assertEqual(manifest.mode, OperationMode.MANIFEST_ONLY)
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            resolve_operation_cli_options(
                parser.parse_args(["--apply-plan", "plan.json", "--preview-sample", "3"])
            )


if __name__ == "__main__":
    unittest.main()
