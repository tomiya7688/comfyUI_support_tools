from __future__ import annotations

import re
from uuid import uuid4

CHARACTER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


# {
#   責務: [create_character_id: 一度生成した後に表示名変更の影響を受けないIDを生成する]
#   処理: [UUIDをcharacter_接頭辞付きの小文字16進文字列として返す]
#   引数: []
#   戻り値: [str: 安定参照用character ID]
# }
def create_character_id() -> str:
    """Create a stable, opaque character identifier independent of its display name."""
    return f"character_{uuid4().hex}"


# {
#   責務: [is_valid_character_id: Character/Outfit IDの共通形式を検証する]
#   処理: [小文字英数字とハイフン/アンダースコアで構成される1〜64文字か判定する]
#   引数: [value: 検証対象ID]
#   戻り値: [bool: ID形式が有効な場合true]
# }
def is_valid_character_id(value: str) -> bool:
    return isinstance(value, str) and CHARACTER_ID_PATTERN.fullmatch(value) is not None
