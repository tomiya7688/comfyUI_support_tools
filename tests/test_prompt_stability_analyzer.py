from __future__ import annotations

import unittest

from comfyui_support_tools.shared.prompt_stability.analyzer import PromptRiskAnalyzer
from comfyui_support_tools.shared.prompt_stability.contracts import (
    ContentMode,
    GuardSettings,
    PromptRiskRequest,
    RiskFactor,
    RiskLevel,
)
from comfyui_support_tools.shared.prompt_stability.policy import (
    StabilityPolicyRegistry,
    StabilityProfile,
)


# {
# 責務: [PromptStabilityAnalyzerTests: SFW/NSFW risk reportの分類を検証する]
# フィールド: [なし]
# 処理: [structural risk, family policy, guard/mode toggleを確認する]
# }
class PromptStabilityAnalyzerTests(unittest.TestCase):
    # {
    # 責務: [test_simple_sfw_is_low_and_complex_sfw_is_high: scene complexityによるrisk差を確認する]
    # 処理: [1: simple requestを解析する, 2: full-body/detail overloadを解析する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_simple_sfw_is_low_and_complex_sfw_is_high(self) -> None:
        analyzer = PromptRiskAnalyzer()
        settings = GuardSettings(enabled=True)
        simple = analyzer.analyze(
            PromptRiskRequest("single girl, smiling", ContentMode.SFW, settings)
        )
        complex_prompt = "full-body, detailed face, detailed hands, hand interaction, complex background, crowded background"
        complex_report = analyzer.analyze(
            PromptRiskRequest(complex_prompt, ContentMode.SFW, settings)
        )
        self.assertIs(simple.overall_risk, RiskLevel.LOW)
        self.assertIs(complex_report.overall_risk, RiskLevel.HIGH)
        self.assertIn(
            "sfw.full_scene_detail", {factor.key for factor in complex_report.risk_factors}
        )

    # {
    # 責務: [test_nsfw_lora_conflict_and_model_family_policy_are_separate: NSFW/LoRA/family profileを区別する]
    # 処理: [1: custom family rulesを登録する, 2: NSFW interaction riskとbackend riskを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_nsfw_lora_conflict_and_model_family_policy_are_separate(self) -> None:
        custom = StabilityProfile(
            ContentMode.NSFW,
            rules=(
                lambda request: (RiskFactor("backend.custom", RiskLevel.MEDIUM, "custom", 0.9),),
            ),
        )
        policies = StabilityPolicyRegistry((custom,))
        analyzer = PromptRiskAnalyzer(policies)
        request = PromptRiskRequest(
            "multiple partners, body interaction, intertwined pose",
            ContentMode.NSFW,
            GuardSettings(enabled=True),
            model_family="sdxl",
            loras=(("style", 0.9, "style"), ("pose", 0.95, "pose")),
        )
        report = analyzer.analyze(request)
        keys = {factor.key for factor in report.risk_factors}
        self.assertIn("nsfw.interaction", keys)
        self.assertIn("lora.style_pose", keys)
        self.assertIn("backend.custom", keys)
        self.assertTrue(report.lora_conflicts)

    # {
    # 責務: [test_guard_and_content_mode_toggles_fail_closed_to_low_risk: OFF/mode checkbox状態を検証する]
    # 処理: [1: guard OFFとSFW-only settingsを解析する, 2: risk adjustmentが無効であることを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_guard_and_content_mode_toggles_fail_closed_to_low_risk(self) -> None:
        analyzer = PromptRiskAnalyzer()
        prompt = "full-body, detailed hands, complex background, holding, embracing"
        off = analyzer.analyze(PromptRiskRequest(prompt, ContentMode.SFW))
        nsfw_unticked = analyzer.analyze(
            PromptRiskRequest(
                prompt, ContentMode.NSFW, GuardSettings(enabled=True, apply_to_nsfw=False)
            )
        )
        self.assertIs(off.overall_risk, RiskLevel.LOW)
        self.assertIs(nsfw_unticked.overall_risk, RiskLevel.LOW)
        self.assertFalse(nsfw_unticked.risk_factors)

    # {
    # 責務: [test_structured_composition_conflict_is_detected: structured fieldsの矛盾を検出する]
    # 処理: [1: composition fieldへ相反する条件を置く, 2: structured conflict reportを確認する]
    # 引数: [self: test case]
    # 戻り値: []
    # }
    def test_structured_composition_conflict_is_detected(self) -> None:
        request = PromptRiskRequest(
            "character",
            ContentMode.SFW,
            GuardSettings(enabled=True),
            structured_prompt={"composition": ("close-up", "full body")},
        )
        report = PromptRiskAnalyzer().analyze(request)
        self.assertIn(
            "conflict.structured.close-up.full body", {factor.key for factor in report.risk_factors}
        )


if __name__ == "__main__":
    unittest.main()
