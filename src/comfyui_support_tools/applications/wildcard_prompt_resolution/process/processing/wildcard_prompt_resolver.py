from __future__ import annotations

import math
import random
import re
from pathlib import Path

from src.comfyui_support_tools.shared.contracts.prompt_resolution_request import (
    PromptResolutionRequest,
)
from src.comfyui_support_tools.shared.contracts.prompt_validation_result import (
    PromptValidationResult,
)

WEIGHTED_LINE_PREFIX = "@weight="
WEIGHTED_LINE_PATTERN = re.compile(r"^@weight=(?P<weight>(?:\d+(?:\.\d+)?|\.\d+))::(?P<text>.*)$")
LOOP_SYNTAX = re.compile(r"\{([^{}]+)\}")
WILDCARD_SYNTAX = re.compile(r"__(.*?)__")
LORA_SYNTAX = re.compile(r"<lora:([^:>]+)(?::[^>]*)?>", re.IGNORECASE)
MAX_RECURSION_DEPTH = 50


# {
#   責務: [parse_wildcard_line: 1行を本文と相対重みに分ける]
#   処理: [重み記法を解析して範囲と本文を検証し, 本文と重みを返す]
#   引数: [line: wildcard fileの行, line_number: 元file上の行番号]
#   戻り値: [tuple[str, float]: 本文と重み]
#   エラー: [ValueError: 記法が不正または本文が空の場合]
# }
def parse_wildcard_line(line: str, line_number: int) -> tuple[str, float]:
    """Parse the optional relative weight and return prompt text plus weight."""
    stripped_line = line.strip()
    if not stripped_line.startswith(WEIGHTED_LINE_PREFIX):
        return stripped_line, 1.0
    match = WEIGHTED_LINE_PATTERN.fullmatch(stripped_line)
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
#   責務: [select_weighted_wildcard_line: 相対重みに基づき候補行を選ぶ]
#   処理: [1: 各候補を検証する, 2: 重み0を除外する, 3: 最大値で正規化して抽選する]
#   引数: [lines: wildcard行または物理行番号付きwildcard行]
#   戻り値: [str: 選択した本文]
#   エラー: [ValueError: 正の重みを持つ候補がない場合]
# }
def select_weighted_wildcard_line(lines: list[str] | list[tuple[int, str]]) -> str:
    """Choose one valid positive-weight line while preserving physical line numbers."""
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
    maximum = max(weight for _, weight in eligible)
    texts = [text for text, _ in eligible]
    weights = [weight / maximum for _, weight in eligible]
    return random.choices(texts, weights=weights, k=1)[0]


# {
#   責務: [expand_prompt_text: providerから渡された参照解決関数を使ってpromptを展開する]
#   処理: [inline候補を選択し, LoRA記法を保護してnested wildcardを再帰展開する]
#   引数: [text: 展開対象, resolve_reference: wildcard参照解決callback]
#   戻り値: [str: 展開済みprompt]
# }
def expand_prompt_text(text: str, resolve_reference) -> str:
    """Expand inline alternatives and delegate nested references to the caller."""
    while match := LOOP_SYNTAX.search(text):
        text = (
            text[: match.start()] + random.choice(match.group(1).split("|")) + text[match.end() :]
        )
    placeholders: dict[str, str] = {}
    text = re.sub(
        r"<[^>]*>",
        lambda match: placeholders.setdefault(f"__LORA_{len(placeholders)}__", match.group(0)),
        text,
    )
    text = WILDCARD_SYNTAX.sub(
        lambda match: (
            match.group(0)
            if match.group(1).startswith("LORA_")
            else resolve_reference(match.group(1).strip("_") + ".txt")
        ),
        text,
    )
    for key, value in placeholders.items():
        text = text.replace(key, value)
    return text


# {
#   責務: [validate_prompt_request: prompt resolution requestの基本入力を検証する]
#   処理: [本文とsource参照の型・空白を確認し, unresolved syntaxをwarningにする]
#   引数: [request: prompt解決request]
#   戻り値: [PromptValidationResult: 検証結果]
# }
def validate_prompt_request(request: PromptResolutionRequest) -> PromptValidationResult:
    """Check request field types and report wildcard-like syntax left in raw text."""
    errors: list[str] = []
    warnings: list[str] = []
    for name, value in (
        ("positive_prompt", request.positive_prompt),
        ("negative_prompt", request.negative_prompt),
    ):
        if not isinstance(value, str):
            errors.append(f"{name} must be a string")
        elif "__" in value or LOOP_SYNTAX.search(value):
            warnings.append(f"{name} contains wildcard-like syntax")
    for name, value in (
        ("positive_source", request.positive_source),
        ("negative_source", request.negative_source),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{name} must be a non-empty string when specified")
    if not isinstance(request.wildcard_root, Path):
        errors.append("wildcard_root must be a pathlib.Path")
    return PromptValidationResult(tuple(errors), tuple(warnings))


# {
#   責務: [lora_references: 展開済みpromptに含まれるLoRA名を重複なしで列挙する]
#   処理: [正promptと負promptのLoRA記法を順序を保って走査する]
#   引数: [positive_prompt: 正prompt, negative_prompt: 負prompt]
#   戻り値: [tuple[str, ...]: LoRA名一覧]
# }
def lora_references(positive_prompt: str, negative_prompt: str) -> tuple[str, ...]:
    """Return unique LoRA names found in positive and negative prompt text."""
    return tuple(
        dict.fromkeys(
            match.group(1).strip()
            for prompt in (positive_prompt, negative_prompt)
            for match in LORA_SYNTAX.finditer(prompt)
        )
    )
