from __future__ import annotations

import unittest

from comfyui_support_tools.shared.prompt_stability.analyzer import PromptRiskAnalyzer
from comfyui_support_tools.shared.prompt_stability.contracts import (
    ApplyMode,
    ComputeBudget,
    ContentMode,
    GuardSettings,
    PromptRiskRequest,
)
from comfyui_support_tools.shared.prompt_stability.planner import PromptAdjustmentPlanner


# {
# 責務: [PromptStabilityPlannerTests: preview/auto adjustmentとretry budgetを検証する]
# フィールド: [なし]
# 処理: [candidate expansion, user locks, bounded quality retryを確認する]
# }
class PromptStabilityPlannerTests(unittest.TestCase):
    # {
    # 責務: [test_suggest_only_preserves_inputs_and_auto_uses_budget: suggest-onlyとauto applyを比較する]
    # 処理: [1: high-risk sceneを解析する, 2: suggest and quality plansを比較する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_suggest_only_preserves_inputs_and_auto_uses_budget(self) -> None:
        prompt = "full-body, detailed hands, complex background, holding"
        base = PromptRiskRequest(
            prompt, ContentMode.SFW, GuardSettings(enabled=True), parameters={"candidate_count": 1}
        )
        analyzer = PromptRiskAnalyzer()
        report = analyzer.analyze(base)
        suggested = PromptAdjustmentPlanner().plan(base, report)
        self.assertEqual(suggested.adjusted_prompt, prompt)
        self.assertEqual(suggested.candidate_count, 1)
        auto_request = PromptRiskRequest(
            prompt,
            ContentMode.SFW,
            GuardSettings(
                enabled=True, apply_mode=ApplyMode.AUTO_APPLY, budget=ComputeBudget.QUALITY
            ),
            parameters={"candidate_count": 1, "steps": 28},
        )
        report = analyzer.analyze(auto_request)
        plan = PromptAdjustmentPlanner().plan(auto_request, report)
        self.assertEqual(plan.candidate_count, 8)
        self.assertEqual(plan.adjusted_parameters["steps"], 32)
        self.assertTrue(plan.requires_preview)

    # {
    # 責務: [test_risk_tolerance_scales_candidate_expansion_within_budget: tolerance別のcandidate budgetを検証する]
    # 処理: [1: 高risk reportを作る, 2: conservative/aggressiveで候補数を比較する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_risk_tolerance_scales_candidate_expansion_within_budget(self) -> None:
        prompt = "full-body, detailed face, detailed hands, complex background"
        analyzer = PromptRiskAnalyzer()
        conservative = PromptRiskRequest(
            prompt,
            ContentMode.SFW,
            GuardSettings(
                enabled=True,
                apply_mode=ApplyMode.AUTO_APPLY,
                budget=ComputeBudget.QUALITY,
                risk_tolerance="conservative",
            ),
        )
        aggressive = PromptRiskRequest(
            prompt,
            ContentMode.SFW,
            GuardSettings(
                enabled=True,
                apply_mode=ApplyMode.AUTO_APPLY,
                budget=ComputeBudget.QUALITY,
                risk_tolerance="aggressive",
            ),
        )
        conservative_plan = PromptAdjustmentPlanner().plan(
            conservative, analyzer.analyze(conservative)
        )
        aggressive_plan = PromptAdjustmentPlanner().plan(aggressive, analyzer.analyze(aggressive))
        self.assertLessEqual(conservative_plan.candidate_count, 4)
        self.assertGreater(aggressive_plan.candidate_count, conservative_plan.candidate_count)
        self.assertLessEqual(aggressive_plan.candidate_count, 16)

    # {
    # 責務: [test_mode_checkbox_user_locks_and_override_are_honored: user control precedenceを確認する]
    # 処理: [1: NSFW off, force original, disabled adjustment, locked valuesを設定する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_mode_checkbox_user_locks_and_override_are_honored(self) -> None:
        request = PromptRiskRequest(
            "detailed face, duplicate, duplicate",
            ContentMode.NSFW,
            GuardSettings(
                enabled=True,
                apply_to_nsfw=False,
                apply_mode=ApplyMode.AUTO_APPLY,
                forced_candidate_count=12,
            ),
            parameters={"candidate_count": 2, "steps": 20},
        )
        report = PromptRiskAnalyzer().analyze(request)
        plan = PromptAdjustmentPlanner().plan(request, report)
        self.assertEqual(plan.candidate_count, 2)
        self.assertFalse(plan.applied)
        override = GuardSettings(
            enabled=True,
            apply_mode=ApplyMode.AUTO_APPLY,
            force_original_prompt=True,
            locked_values={"steps": 21},
        )
        request = PromptRiskRequest(
            "same, same, crowded group, full-body, detailed hands, complex background",
            ContentMode.SFW,
            override,
            parameters={"steps": 20},
        )
        report = PromptRiskAnalyzer().analyze(request)
        plan = PromptAdjustmentPlanner().plan(request, report)
        self.assertEqual(plan.adjusted_prompt, request.prompt)
        self.assertEqual(plan.adjusted_parameters["steps"], 21)

    # {
    # 責務: [test_rewriter_and_profile_negative_augmentation_are_model_aware: policy adapterとnegative supportを検証する]
    # 処理: [1: model rewrite hookとprofile negativeを登録する, 2: mode非対応ではnegative追加をしない]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_rewriter_and_profile_negative_augmentation_are_model_aware(self) -> None:
        from comfyui_support_tools.shared.prompt_stability.policy import (
            StabilityPolicyRegistry,
            StabilityProfile,
        )

        policies = StabilityPolicyRegistry(
            (
                StabilityProfile(
                    ContentMode.SFW,
                    preferred_backend="stable-backend",
                    negative_terms=("bad hands",),
                ),
            )
        )
        planner = PromptAdjustmentPlanner(
            policies, rewriter=lambda prompt, report, family: f"{family}: {prompt}"
        )
        request = PromptRiskRequest(
            "busy group scene",
            ContentMode.SFW,
            GuardSettings(enabled=True, apply_mode=ApplyMode.AUTO_APPLY),
            model_family="sdxl",
        )
        report = PromptRiskAnalyzer(policies).analyze(request)
        plan = planner.plan(request, report)
        self.assertTrue(plan.adjusted_prompt.startswith("sdxl:"))
        self.assertIn("bad hands", plan.adjusted_negative_prompt)
        self.assertEqual(plan.backend_hint, "stable-backend")
        no_negative = PromptRiskRequest(
            request.prompt, ContentMode.SFW, request.settings, negative_supported=False
        )
        plan = planner.plan(no_negative, PromptRiskAnalyzer(policies).analyze(no_negative))
        self.assertEqual(plan.adjusted_negative_prompt, "")


if __name__ == "__main__":
    unittest.main()
