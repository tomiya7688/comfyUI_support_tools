from __future__ import annotations

import math
import random
import re

_WEIGHTED_LINE_PREFIX = "@weight="
_WEIGHTED_LINE_PATTERN = re.compile(r"^@weight=(?P<weight>(?:\d+(?:\.\d+)?|\.\d+))::(?P<text>.*)$")


# {
#   責務: [parse_wildcard_line: 行を本文と相対重みに分ける]
#   処理: [1: 重み記法を検出する, 2: 数値の範囲と本文を検証する, 3: 本文と重みを返す]
#   引数: [line: wildcardファイルの1行, line_number: 元ファイル上の行番号]
#   戻り値: [tuple[str, float]: 本文と相対重み]
#   エラー: [ValueError: 重み記法または本文が不正な場合]
# }
def parse_wildcard_line(line: str, line_number: int) -> tuple[str, float]:
    stripped_line = line.strip()
    if not stripped_line.startswith(_WEIGHTED_LINE_PREFIX):
        return stripped_line, 1.0

    match = _WEIGHTED_LINE_PATTERN.fullmatch(stripped_line)
    if match is None:
        raise ValueError(
            f"Invalid weighted wildcard line {line_number}: "
            "expected '@weight=<non-negative number>::<text>'"
        )

    raw_weight = match.group("weight")
    weight = float(raw_weight)
    text = match.group("text").strip()
    if not math.isfinite(weight):
        raise ValueError(f"Invalid weighted wildcard line {line_number}: weight must be finite")
    if weight == 0.0 and re.search(r"[1-9]", raw_weight):
        raise ValueError(
            f"Invalid weighted wildcard line {line_number}: weight is smaller than the supported range"
        )
    if not text:
        raise ValueError(f"Invalid weighted wildcard line {line_number}: text must not be empty")
    return text, weight


# {
#   責務: [select_weighted_wildcard_line: 候補行から相対重みに基づいて1行を選ぶ]
#   処理: [1: 元の行番号を保って各行を検証する, 2: 重み0の行を除外する, 3: 確率に従い本文を返す]
#   引数: [lines: ワイルドカード行の文字列または元行番号と行文字列の組]
#   戻り値: [str: 選択した行の本文]
#   エラー: [ValueError: 全行の重みが0または行の記法が不正な場合]
# }
def select_weighted_wildcard_line(lines: list[str] | list[tuple[int, str]]) -> str:
    candidates = [
        parse_wildcard_line(line, line_number)
        for line_number, line in (
            item if isinstance(item, tuple) else (index, item)
            for index, item in enumerate(lines, start=1)
        )
        if line.strip()
    ]
    eligible = [(text, weight) for text, weight in candidates if weight > 0]
    if not eligible:
        raise ValueError("Wildcard file has no selectable lines with a positive weight")

    max_weight = max(weight for _, weight in eligible)
    texts = [text for text, _ in eligible]
    normalized_weights = [weight / max_weight for _, weight in eligible]
    return random.choices(texts, weights=normalized_weights, k=1)[0]
