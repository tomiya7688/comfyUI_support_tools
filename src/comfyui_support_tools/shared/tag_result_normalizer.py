"""Pure normalization of common and PixAI Tagger response payloads."""

from __future__ import annotations

import math
from typing import Any

from comfyui_support_tools.shared.contracts.inspector_contracts import (
    NormalizedTagResult,
    ScoredLabel,
)
from comfyui_support_tools.shared.contracts.tagger_backend import resolve_backend

MAX_LABELS = 2000
MAX_LABEL_CHARS = 16384
MAX_CAPTION = 8192


# {
#   責務: [_validate_label: tag nameとconfidenceを境界値・型・文字数に照らして検証する]
#   処理: [制御文字、空名、長すぎる名前、非finite/out-of-range scoreを拒否しnameをtrimする]
#   引数: [name: tag名候補, score: confidence候補]
#   戻り値: [ScoredLabel: 検証済みtagとfloat score]
#   エラー: [ValueError: nameまたはscoreが許容範囲外]
# }
def _validate_label(name: Any, score: Any) -> ScoredLabel:
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 256
        or any(ord(char) < 32 for char in name)
        or isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or not 0 <= score <= 1
    ):
        raise ValueError("Invalid tag name or confidence")
    return ScoredLabel(name.strip(), float(score))


# {
#   責務: [_dedupe: 同名tagを初出順のまま一つにまとめる]
#   処理: [重複時は最大scoreを保持し、出力順は最初の出現順とする]
#   引数: [entries: 検証済みScoredLabel tuple]
#   戻り値: [deduplicated entries: 一意nameのtuple]
# }
def _dedupe(entries: tuple[ScoredLabel, ...]) -> tuple[ScoredLabel, ...]:
    best: dict[str, ScoredLabel] = {}
    order: list[str] = []
    for entry in entries:
        if entry.name not in best:
            order.append(entry.name)
            best[entry.name] = entry
        elif entry.score > best[entry.name].score:
            best[entry.name] = entry
    return tuple(best[name] for name in order)


# {
#   責務: [_entries: string/map/list形式のtag値をScoredLabel tupleへ変換する]
#   処理: [未指定を空tuple、comma-separated stringをscore 1、record/mapを検証して重複排除する]
#   引数: [value: backend payload内のcategory値]
#   戻り値: [entries: deduplicated ScoredLabel tuple]
#   エラー: [ValueError: unsupported shape、too many entries、invalid label/score]
# }
def _entries(value: Any) -> tuple[ScoredLabel, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        labels = (part.strip() for part in value.split(","))
        return _dedupe(tuple(_validate_label(label, 1.0) for label in labels if label))
    if isinstance(value, dict):
        if len(value) > MAX_LABELS or not all(
            isinstance(score, (int, float)) and not isinstance(score, bool)
            for score in value.values()
        ):
            raise ValueError("Unsupported tag mapping")
        return _dedupe(tuple(_validate_label(name, score) for name, score in value.items()))
    if isinstance(value, list):
        if len(value) > MAX_LABELS:
            raise ValueError("Too many tags")
        results = []
        for record in value:
            if isinstance(record, str):
                results.append(_validate_label(record, 1.0))
            elif isinstance(record, dict):
                results.append(
                    _validate_label(
                        record.get("name", record.get("tag")),
                        record.get("confidence", record.get("score", 1.0)),
                    )
                )
            else:
                raise ValueError("Unsupported tag entry")
        return _dedupe(tuple(results))
    raise ValueError("Unsupported tag response")


# {
#   責務: [_unwrap: result/dataだけの単一key wrapperを最大4段まで剥がす]
#   処理: [error objectを拒否し、wrapper以外のobjectまたはscalarをそのまま返す]
#   引数: [payload: backend response payload]
#   戻り値: [unwrapped payload]
#   エラー: [ValueError: payloadにerror keyがある]
# }
def _unwrap(payload: Any) -> Any:
    value = payload
    for _ in range(4):
        if not isinstance(value, dict):
            return value
        if "error" in value:
            raise ValueError("Tagger returned an error object")
        wrapper = next(
            (name for name in ("result", "data") if name in value and len(value) == 1), None
        )
        if wrapper is None:
            return value
        value = value[wrapper]
    return value


# {
#   責務: [_category_node: nested tags objectにcategory keysがあればそのobjectを選ぶ]
#   処理: [category構造を識別できる場合だけtagsを返し、それ以外はnodeを維持する]
#   引数: [node: unwrapped payload node]
#   戻り値: [category candidateまたは元node]
# }
def _category_node(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    tags = node.get("tags")
    category_names = {
        "general",
        "general_tags",
        "character",
        "character_tags",
        "copyright",
        "copyright_tags",
        "rating",
        "ratings",
    }
    return tags if isinstance(tags, dict) and category_names.intersection(tags) else node


# {
#   責務: [_pick: mappingから候補key順で最初に存在する値を選ぶ]
#   処理: [nodeがdictの場合のみnamesを順に検索する]
#   引数: [node: candidate mapping, names: 候補key tuple]
#   戻り値: [最初の一致value、またはNone]
# }
def _pick(node: Any, names: tuple[str, ...]) -> Any:
    if isinstance(node, dict):
        return next((node[name] for name in names if name in node), None)
    return None


# {
#   責務: [_filtered: score threshold以上のtagを残し、文字数上限を検査する]
#   処理: [順序を保ってscoreを比較し、採用name総文字数が上限超過なら拒否する]
#   引数: [entries: ScoredLabel tuple, threshold: inclusive score threshold]
#   戻り値: [filtered ScoredLabel tuple]
#   エラー: [ValueError: 採用tagの文字数合計が上限を超過]
# }
def _filtered(entries: tuple[ScoredLabel, ...], threshold: float) -> tuple[ScoredLabel, ...]:
    values = tuple(entry for entry in entries if entry.score >= threshold)
    if sum(len(entry.name) for entry in values) > MAX_LABEL_CHARS:
        raise ValueError("Tag result exceeds 16384 characters")
    return values


# {
#   責務: [parse_tag_result: backend応答のtag形式を共通NormalizedTagResultへ変換する]
#   処理: [threshold検査、wrapper/category解析、label validation、category別filter、backend解決を行う]
#   引数: [payload: response body, threshold: 通常tag基準, character_threshold: character基準, backend_id/url: backend識別情報, model: model名]
#   戻り値: [NormalizedTagResult: category tags/scores、caption、rating、backend/model]
#   エラー: [ValueError: unsupported/error payload、invalid values、backend/threshold不一致]
# }
def parse_tag_result(
    payload: Any,
    threshold: float,
    character_threshold: float,
    backend_id: str = "auto_http",
    url: str = "",
    model: str = "",
) -> NormalizedTagResult:
    if not all(0 <= value <= 1 for value in (threshold, character_threshold)):
        raise ValueError("Tag thresholds must be between 0 and 1")
    node = _unwrap(payload)
    category = _category_node(node)
    if isinstance(category, dict):
        general = _pick(category, ("general", "general_tags"))
        if general is None:
            fallback = _pick(node, ("tag", "tags"))
            if isinstance(fallback, dict) and {
                "general",
                "general_tags",
                "character",
                "character_tags",
                "copyright",
                "copyright_tags",
                "rating",
                "ratings",
            }.intersection(fallback):
                general = _pick(fallback, ("general", "general_tags"))
            else:
                general = fallback
        characters = _pick(category, ("character", "characters", "character_tags"))
        copyrights = _pick(category, ("copyright", "copyrights", "copyright_tags"))
        ratings = _pick(category, ("rating", "ratings"))
        caption = _pick(node, ("caption",))
    else:
        general, characters, copyrights, ratings, caption = category, None, None, None, ""

    if (
        general is None
        and isinstance(node, dict)
        and node
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in node.values()
        )
    ):
        general = node
    if isinstance(caption, str):
        if len(caption) > MAX_CAPTION:
            raise ValueError("Caption exceeds 8192 characters")
        caption = caption.strip()
        if general is None and "," in caption:
            general = caption
    elif caption is None:
        caption = ""
    else:
        raise ValueError("Caption must be a string")
    if (
        isinstance(node, dict)
        and node
        and not any((general, characters, copyrights, ratings, caption))
    ):
        raise ValueError("Unsupported tag response")

    general_all, character_all = _entries(general), _entries(characters)
    copyright_all, rating_all = _entries(copyrights), _entries(ratings)
    resolved_backend = resolve_backend(backend_id, url).id if url else backend_id
    return NormalizedTagResult(
        content_tags=tuple(item.name for item in _filtered(general_all, threshold)),
        character_tags=tuple(item.name for item in _filtered(character_all, character_threshold)),
        copyright_tags=tuple(item.name for item in _filtered(copyright_all, threshold)),
        rating=max(rating_all, key=lambda item: item.score).name if rating_all else "",
        caption=caption,
        content_scores=general_all,
        character_scores=character_all,
        rating_scores=rating_all,
        backend=resolved_backend,
        model=model,
    )


# {
#   責務: [parse_tags: legacy Inspector callers向けにflat tags adapterを提供する]
#   処理: [通常tagとcharacterのthresholdを同じ値にしてparse_tag_resultへ委譲する]
#   引数: [payload: Tagger response payload, threshold: 共通tag score threshold]
#   戻り値: [content_tags: normalized content tag name tuple]
# }
def parse_tags(payload: Any, threshold: float) -> tuple[str, ...]:
    """Legacy flat-tag adapter retained for existing Inspector callers."""
    return parse_tag_result(payload, threshold, threshold).content_tags
