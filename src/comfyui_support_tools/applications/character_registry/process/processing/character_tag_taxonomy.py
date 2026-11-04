from __future__ import annotations

import re

IDENTITY_PHRASES = (
    "hair",
    "eyes",
    "eye",
    "ponytail",
    "twintails",
    "braid",
    "ahoge",
    "bob cut",
    "hime cut",
    "freckles",
    "mole",
    "scar",
    "horn",
    "animal ears",
    "tail",
    "fang",
    "eyepatch",
    "glasses",
)
OUTFIT_PHRASES = (
    "shirt",
    "t shirt",
    "blouse",
    "dress",
    "skirt",
    "pants",
    "shorts",
    "uniform",
    "jacket",
    "coat",
    "sweater",
    "hoodie",
    "sleeves",
    "socks",
    "shoes",
    "boots",
    "hat",
    "ribbon",
    "necklace",
    "bra",
    "panties",
    "underwear",
    "bikini",
    "swimsuit",
    "clothing",
    "outfit",
    "kimono",
    "armor",
)
CONTEXT_PHRASES = (
    "standing",
    "sitting",
    "kneeling",
    "lying",
    "walking",
    "running",
    "jumping",
    "looking at viewer",
    "looking away",
    "smile",
    "smiling",
    "frown",
    "blush",
    "open mouth",
    "closed eyes",
    "holding",
    "indoors",
    "outdoors",
    "bedroom",
    "classroom",
    "city",
    "beach",
    "night",
    "day",
    "sunlight",
    "backlighting",
    "portrait",
    "close up",
    "full body",
    "from behind",
    "cowboy shot",
    "upper body",
)


# {
#   責務: [_normalized_tokens: tagを比較用token列へ変換する]
#   処理: [casefoldし, 区切り文字を空白化し, 英数字tokenを取り出す]
#   引数: [tag: caption tag]
#   戻り値: [tuple[str, ...]: 正規化token列]
# }
def _normalized_tokens(tag: str) -> tuple[str, ...]:
    """Normalize separators while preserving word boundaries for classification."""
    normalized = tag.casefold().replace("_", " ").replace("-", " ")
    return tuple(re.findall(r"[a-z0-9]+|[^\W\d_]+", normalized, flags=re.UNICODE))


# {
#   責務: [_contains_phrase: normalized tag内のphraseをtoken境界付きで探す]
#   処理: [phrase token列がtag token列の連続区間と一致するか返す]
#   引数: [tokens: normalized tag, phrase: 検索phrase]
#   戻り値: [bool: phraseが含まれる場合true]
# }
def _contains_phrase(tokens: tuple[str, ...], phrase: str) -> bool:
    phrase_tokens = tuple(phrase.split())
    return any(
        tokens[index : index + len(phrase_tokens)] == phrase_tokens
        for index in range(len(tokens) - len(phrase_tokens) + 1)
    )


# {
#   責務: [classify_character_tag: tagをidentity/outfit/context/unclassifiedへ慎重に分類する]
#   処理: [境界一致するidentity, clothing, scene phraseを探し, 未知tagはunclassifiedに残す]
#   引数: [tag: caption tag]
#   戻り値: [str: identity, outfit, context, unclassifiedのいずれか]
# }
def classify_character_tag(tag: str) -> str:
    """Classify known identity, clothing, and scene terms; preserve unknown tags for review."""
    tokens = _normalized_tokens(tag)
    if any(_contains_phrase(tokens, phrase) for phrase in OUTFIT_PHRASES):
        return "outfit"
    if any(_contains_phrase(tokens, phrase) for phrase in CONTEXT_PHRASES):
        return "context"
    if any(_contains_phrase(tokens, phrase) for phrase in IDENTITY_PHRASES):
        return "identity"
    return "unclassified"
