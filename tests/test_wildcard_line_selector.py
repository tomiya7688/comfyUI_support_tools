from __future__ import annotations

import unittest
from unittest import mock

from src.comfyui_support_tools.applications.wildcard_prompt_resolution.api import (
    parse_wildcard_line,
)
from src.comfyui_support_tools.applications.wildcard_prompt_resolution.process.processing.wildcard_prompt_resolver import (
    select_weighted_wildcard_line,
)


# {
#   責務: [WeightedWildcardLineSelectorTests: 重み付きwildcard行選択を検証する]
#   処理: [1: 相対重みを検証する, 2: 通常行とゼロ重みを確認する, 3: 行番号と範囲外重みを検証する]
#   フィールド: []
# }
class WeightedWildcardLineSelectorTests(unittest.TestCase):
    # {
    #   責務: [test_relative_weights_are_normalized: 重みと既定行の選択比率を検証する]
    #   処理: [1: 選択結果を固定し, 2: 抽選へ渡す相対重みを確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_relative_weights_are_normalized(self):
        with mock.patch(
            "src.comfyui_support_tools.applications.wildcard_prompt_resolution.process.processing.wildcard_prompt_resolver.random.choices",
            side_effect=lambda choices, weights, k: [choices[0]],
        ) as choose:
            selected = select_weighted_wildcard_line(
                ["@weight=3::weighted prompt", "ordinary prompt"]
            )

        self.assertEqual(selected, "weighted prompt")
        self.assertEqual(choose.call_args.kwargs["weights"], [1.0, 1.0 / 3.0])

    # {
    #   責務: [test_default_and_zero_weights: 既定重みと選択対象外行を検証する]
    #   処理: [1: 通常のLoRA記法を保ち, 2: 重み0の行が抽選から外れることを確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_default_and_zero_weights(self):
        lora_line = "<lora:character:0.8>"
        with mock.patch(
            "src.comfyui_support_tools.applications.wildcard_prompt_resolution.process.processing.wildcard_prompt_resolver.random.choices",
            side_effect=lambda choices, weights, k: [choices[0]],
        ) as choose:
            selected = select_weighted_wildcard_line(["@weight=0::disabled", lora_line])

        self.assertEqual(selected, lora_line)
        self.assertEqual(choose.call_args.args[0], [lora_line])
        self.assertEqual(choose.call_args.kwargs["weights"], [1.0])

    # {
    #   責務: [test_invalid_weights_raise_clear_errors: 不正な重み記法を拒否する]
    #   処理: [1: 不正な宣言と全行無効の入力を個別に検証する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_invalid_weights_raise_clear_errors(self):
        invalid_inputs = [
            ["@weight=-1::negative"],
            ["@weight=bad::malformed"],
            ["@weight=1::"],
            ["@weight=0." + "0" * 400 + "1::underflow"],
            ["@weight=0::disabled"],
        ]
        for lines in invalid_inputs:
            with self.subTest(lines=lines):
                with self.assertRaises(ValueError):
                    select_weighted_wildcard_line(lines)

    # {
    #   責務: [test_source_line_numbers_are_preserved: 空行を含む元ファイルの行番号を保持する]
    #   処理: [1: 物理行番号付きの候補を渡す, 2: 不正記法のエラーが元の行番号を示すことを確認する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_source_line_numbers_are_preserved(self):
        with self.assertRaisesRegex(ValueError, "line 5"):
            select_weighted_wildcard_line([(2, "valid prompt"), (5, "@weight=bad::invalid prompt")])

    # {
    #   責務: [test_sequential_prompt_line_is_parsed: 順次promptから重み記法を分離する]
    #   処理: [1: 正の重み行と0重み行を個別に解析する]
    #   引数: [self: unittest test instance]
    #   戻り値: []
    # }
    def test_sequential_prompt_line_is_parsed(self):
        self.assertEqual(parse_wildcard_line("@weight=2::prompt", 8), ("prompt", 2.0))
        self.assertEqual(parse_wildcard_line("@weight=0::disabled", 9), ("disabled", 0.0))


if __name__ == "__main__":
    unittest.main()
