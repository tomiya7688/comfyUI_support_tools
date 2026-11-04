import unittest
from pathlib import Path
from unittest import mock

from src.comfyui_support_tools.applications.wildcard_prompt_resolution.api import (
    load_sequential_prompt_lines,
    resolve_prompt,
    validate_prompt,
)
from src.comfyui_support_tools.applications.wildcard_prompt_resolution.process.processing import (
    wildcard_prompt_resolver,
)
from src.comfyui_support_tools.applications.wildcard_prompt_resolution.process.messenger import (
    wildcard_data_messenger,
)
from src.comfyui_support_tools.shared.contracts.prompt_resolution_request import (
    PromptResolutionRequest,
)
from src.comfyui_support_tools.shared.contracts.resolved_prompt import ResolvedPrompt

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "wildcard_prompt_resolution"


# {
#   責務: [WildcardPromptResolutionApiTests: prompt resolution Application APIの契約を検証する]
#   処理: [代表的なwildcard展開, LoRA検出, validation, 順次source読込を確認する]
#   フィールド: []
# }
class WildcardPromptResolutionApiTests(unittest.TestCase):
    # {
    #   責務: [test_cache_keys_follow_platform_case_rules: cache keyがOSのcase規則を使うことを確認する]
    #   処理: [normcaseを大文字小文字保存に置き換え, 異なるpath表記が別keyになることを確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_cache_keys_follow_platform_case_rules(self):
        """Do not merge distinct wildcard paths before platform normalization."""
        with mock.patch.object(
            wildcard_data_messenger.os.path,
            "normcase",
            side_effect=lambda path: path,
        ):
            uppercase = wildcard_data_messenger._wildcard_cache_key("Character.txt", FIXTURE_ROOT)
            lowercase = wildcard_data_messenger._wildcard_cache_key("character.txt", FIXTURE_ROOT)

        self.assertNotEqual(uppercase, lowercase)

    # {
    #   責務: [test_resolve_prompt_returns_backend_independent_result: wildcardとLoRA参照を解決する]
    #   処理: [fixture sourceからResolvedPromptを作り, promptとprovenanceを検証する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_resolve_prompt_returns_backend_independent_result(self):
        """Check nested expansion, LoRA extraction, and source provenance."""
        result = resolve_prompt(
            PromptResolutionRequest(positive_source="entry.txt", wildcard_root=FIXTURE_ROOT)
        )

        self.assertIsInstance(result, ResolvedPrompt)
        self.assertEqual(result.positive_prompt, "blue shirt <lora:fixture_character:0.8>")
        self.assertEqual(result.resolved_loras, ("fixture_character",))
        self.assertEqual(
            result.resolved_wildcards,
            (
                str((FIXTURE_ROOT / "entry.txt").as_posix()),
                str((FIXTURE_ROOT / "nested.txt").as_posix()),
            ),
        )

    # {
    #   責務: [test_character_wrapper_keeps_lora_and_tags_consistent: 同一request内でwrapper構成要素を一度だけ解決する]
    #   処理: [LoRA参照wildcardとcharacter tag wildcardをwrapperから呼び, 同じwrapperの反復結果が一致することを確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_character_wrapper_keeps_lora_and_tags_consistent(self):
        """Reuse each wildcard choice within one prompt resolution request."""
        with mock.patch.object(
            wildcard_prompt_resolver.random,
            "choices",
            side_effect=lambda choices, weights, k: [choices[0]],
        ) as choose:
            result = resolve_prompt(
                PromptResolutionRequest(
                    positive_prompt=(
                        "__character_with_lora/aoba_moca__ __character_with_lora/aoba_moca__"
                    ),
                    wildcard_root=FIXTURE_ROOT,
                )
            )

        expected_wrapper = "<lora:aoba_moca:0.8> blue hair green eyes"
        self.assertEqual(result.positive_prompt, f"{expected_wrapper} {expected_wrapper}")
        self.assertEqual(choose.call_count, 3)
        self.assertEqual(result.resolved_loras, ("aoba_moca",))

    # {
    #   責務: [test_validation_reports_unresolved_wildcard_syntax: 未解決記法をwarningにする]
    #   処理: [raw promptを検証してvalid状態とwarningを確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_validation_reports_unresolved_wildcard_syntax(self):
        """Keep unresolved syntax visible to callers as a validation warning."""
        result = validate_prompt(PromptResolutionRequest(positive_prompt="__missing__"))

        self.assertTrue(result.is_valid)
        self.assertEqual(result.warnings, ("positive_prompt contains wildcard-like syntax",))

    # {
    #   責務: [test_sequential_sources_preserve_physical_lines: 順次prompt sourceの行順と行番号を保つ]
    #   処理: [fixtureから行を読み, 空行を除いた物理行番号を検証する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_sequential_sources_preserve_physical_lines(self):
        """Preserve source order and original line numbers for sequential jobs."""
        result = load_sequential_prompt_lines("sequential.txt", FIXTURE_ROOT)

        self.assertEqual(
            result,
            [
                (str((FIXTURE_ROOT / "sequential.txt").as_posix()), 1, "@weight=0::disabled"),
                (str((FIXTURE_ROOT / "sequential.txt").as_posix()), 2, "first prompt"),
                (str((FIXTURE_ROOT / "sequential.txt").as_posix()), 4, "@weight=3::third prompt"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
