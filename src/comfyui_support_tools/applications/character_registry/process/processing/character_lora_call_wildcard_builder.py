from __future__ import annotations

import re

from src.comfyui_support_tools.applications.wildcard_prompt_resolution.api import (
    parse_wildcard_line,
)
from src.comfyui_support_tools.shared.contracts.character_id import is_valid_character_id

LORA_CALL_PATTERN = re.compile(
    r"<lora:(?P<name>[^:<>\r\n]+)(?::(?P<strength>[+-]?(?:\d+(?:\.\d*)?|\.\d+)))?>",
    re.IGNORECASE,
)


# {
#   責務: [build_character_lora_call_wildcard: Character IDとLoRA候補行を安全なwildcard file bundleへ変換する]
#   処理: [行重みとLoRA記法を検証し, wildcard root相対pathと本文を返す]
#   引数: [character_id: stable ID, content: 重み付きLoRA呼び出し候補]
#   戻り値: [dict[str, str]: 相対wildcard pathと本文]
#   エラー: [ValueError: ID、候補行、重み、LoRA記法が不正な場合]
# }
def build_character_lora_call_wildcard(character_id: str, content: str) -> dict[str, str]:
    """Validate weighted LoRA-call choices and build their character-scoped file."""
    if not is_valid_character_id(character_id):
        raise ValueError("character_idが不正です")
    if not isinstance(content, str):
        raise ValueError("LoRA呼び出し内容は文字列で指定してください")

    source_lines = content.splitlines()
    valid_lines: list[str] = []
    has_positive_weight = False
    for line_number, source_line in enumerate(source_lines, start=1):
        stripped_line = source_line.strip()
        if not stripped_line:
            continue
        lora_call, weight = parse_wildcard_line(stripped_line, line_number)
        match = LORA_CALL_PATTERN.fullmatch(lora_call)
        if match is None or not match.group("name").strip():
            raise ValueError(
                f"LoRA呼び出し行{line_number}は<lora:モデル名:強度>形式で指定してください"
            )
        if match.group("strength") is not None:
            strength = float(match.group("strength"))
            if not (-float("inf") < strength < float("inf")):
                raise ValueError(f"LoRA強度が不正です: line {line_number}")
        has_positive_weight = has_positive_weight or weight > 0
        valid_lines.append(stripped_line)

    if not valid_lines:
        raise ValueError("LoRA呼び出し候補を1行以上指定してください")
    if not has_positive_weight:
        raise ValueError("LoRA呼び出し候補には正の重みが必要です")
    return {f"anime_character_lora/{character_id}.txt": "\n".join(valid_lines) + "\n"}
