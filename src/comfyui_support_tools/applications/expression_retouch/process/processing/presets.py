"""Extensible natural-language aliases for structured expression presets."""

from __future__ import annotations

from comfyui_support_tools.shared.contracts.expression_retouch import ExpressionPreset

DEFAULT_ALIASES = {
    "neutral": ExpressionPreset.NEUTRAL,
    "真顔": ExpressionPreset.NEUTRAL,
    "slight smile": ExpressionPreset.SLIGHT_SMILE,
    "微笑み": ExpressionPreset.SLIGHT_SMILE,
    "smile": ExpressionPreset.SMILE,
    "笑顔": ExpressionPreset.SMILE,
    "laugh": ExpressionPreset.LAUGH,
    "大笑い": ExpressionPreset.LAUGH,
    "angry": ExpressionPreset.ANGRY,
    "怒り": ExpressionPreset.ANGRY,
    "sad": ExpressionPreset.SAD,
    "悲しい": ExpressionPreset.SAD,
    "crying": ExpressionPreset.CRYING,
    "泣き顔": ExpressionPreset.CRYING,
    "surprised": ExpressionPreset.SURPRISED,
    "驚き": ExpressionPreset.SURPRISED,
    "embarrassed": ExpressionPreset.EMBARRASSED,
    "照れ": ExpressionPreset.EMBARRASSED,
    "worried": ExpressionPreset.WORRIED,
    "心配": ExpressionPreset.WORRIED,
    "sleepy": ExpressionPreset.SLEEPY,
    "眠い": ExpressionPreset.SLEEPY,
    "wink left": ExpressionPreset.WINK_LEFT,
    "左目ウインク": ExpressionPreset.WINK_LEFT,
    "wink right": ExpressionPreset.WINK_RIGHT,
    "右目ウインク": ExpressionPreset.WINK_RIGHT,
    "smirk": ExpressionPreset.SMIRK,
    "shout": ExpressionPreset.SHOUT,
    "叫び": ExpressionPreset.SHOUT,
    "angry but cute": ExpressionPreset.ANGRY,
    "sad expression with teary eyes": ExpressionPreset.CRYING,
    "wink with an open-mouth smile": ExpressionPreset.WINK_LEFT,
}


# {
#   責務: [resolve_expression_target: map an exact natural-language phrase to a stable target]
#   処理: [1: normalize whitespace/case, 2: resolve a registered alias, 3: preserve caller preset when no alias matches]
#   引数: [text: user-entered expression phrase, fallback: selected preset, aliases: optional alias registry]
#   戻り値: [ExpressionPreset: structured target]
# }
def resolve_expression_target(
    text: str,
    fallback: ExpressionPreset,
    aliases: dict[str, ExpressionPreset] | None = None,
) -> ExpressionPreset:
    registry = DEFAULT_ALIASES if aliases is None else aliases
    normalized = " ".join(text.casefold().split())
    return registry.get(normalized, fallback)
