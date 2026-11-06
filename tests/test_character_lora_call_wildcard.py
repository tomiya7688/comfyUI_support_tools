import tempfile
import unittest
from pathlib import Path

from src.comfyui_support_tools.applications.character_registry.api import (
    build_character_lora_call_wildcard,
    write_character_lora_call_wildcard,
)


# {
#   責務: [CharacterLoraCallWildcardTests: Characterごとの重み付きLoRA呼び出しwildcard builder/APIを検証する]
#   フィールド: [unittest assertion機能]
#   処理: [候補形式の受入れ、誤入力拒否、指定rootへの保存を確認する]
# }
class CharacterLoraCallWildcardTests(unittest.TestCase):
    """Validate Character-scoped weighted local LoRA-call files."""

    # {
    #   責務: [test_builder_preserves_weighted_lora_choices: 重み付き候補をCharacter固有のwildcardへ変換する]
    #   処理: [候補行を解析し, 相対pathと改行終端の本文を確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_builder_preserves_weighted_lora_choices(self):
        """Keep relative line weights and each model's local name and strength."""
        files = build_character_lora_call_wildcard(
            "aoba_moca",
            "@weight=3::<lora:model_a:0.8>\n<lora:model_b:0.7>",
        )

        self.assertEqual(
            files,
            {
                "anime_character_lora/aoba_moca.txt": "@weight=3::<lora:model_a:0.8>\n"
                "<lora:model_b:0.7>\n"
            },
        )

    # {
    #   責務: [test_builder_rejects_non_lora_prompt_content: LoRA呼び出し以外のprompt本文を拒否する]
    #   処理: [通常tagやwildcardを含む行でValueErrorを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_builder_rejects_non_lora_prompt_content(self):
        """Reject arbitrary prompt syntax in a file reserved for LoRA calls."""
        for content in ("red hair", "__other_lora__", "<lora:model:0.8>, red hair"):
            with self.subTest(content=content), self.assertRaises(ValueError):
                build_character_lora_call_wildcard("aoba_moca", content)

    # {
    #   責務: [test_builder_rejects_all_zero_weights: 選択できないLoRA候補だけの内容を拒否する]
    #   処理: [重み0の候補のみを渡してValueErrorを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_builder_rejects_all_zero_weights(self):
        """Require at least one selectable LoRA-call candidate."""
        with self.assertRaisesRegex(ValueError, "正の重み"):
            build_character_lora_call_wildcard("aoba_moca", "@weight=0::<lora:model_a:0.8>")

    # {
    #   責務: [test_writer_saves_character_scoped_mapping: 指定rootへLoRA呼び出しファイルを保存する]
    #   処理: [API writerを実行し, 出力pathとUTF-8本文を読み直す]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_writer_saves_character_scoped_mapping(self):
        """Write the validated mapping beneath the explicit wildcard root."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            written = write_character_lora_call_wildcard(
                "aoba_moca",
                "<lora:model_a:0.8>",
                root,
            )

            expected_path = root / "anime_character_lora" / "aoba_moca.txt"
            self.assertEqual(len(written), 1)
            self.assertEqual(written[0].resolve(), expected_path.resolve())
            self.assertEqual(written[0].read_text(encoding="utf-8"), "<lora:model_a:0.8>\n")


if __name__ == "__main__":
    unittest.main()
