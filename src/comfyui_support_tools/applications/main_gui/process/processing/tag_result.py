"""Normalize old PixAI and future common Tagger responses without mixing Style into content."""
import math

from comfyui_support_tools.shared.contracts.inspector_contracts import NormalizedTagResult, ScoredLabel
from comfyui_support_tools.shared.contracts.tagger_backend import resolve_backend

MAX_LABELS = 2000
MAX_LABEL_CHARS = 16384
MAX_CAPTION = 8192


def _validate_label(name, score):
    if (not isinstance(name, str) or not name.strip() or len(name) > 256
            or any(ord(char) < 32 for char in name)
            or isinstance(score, bool) or not isinstance(score, (int, float))
            or not math.isfinite(score) or not 0 <= score <= 1):
        raise ValueError("Invalid tag name or confidence")
    return ScoredLabel(name.strip(), float(score))


def _entries(value):
    if value is None:
        return ()
    if isinstance(value, str):
        labels = [part.strip() for part in value.split(",") if part.strip()]
        return tuple(_validate_label(label, 1.0) for label in labels)
    if isinstance(value, dict):
        if len(value) > MAX_LABELS:
            raise ValueError("Too many tags")
        if all(isinstance(score, (int, float)) and not isinstance(score, bool) for score in value.values()):
            return tuple(_validate_label(name, score) for name, score in value.items())
        raise ValueError("Unsupported tag mapping")
    if isinstance(value, list):
        if len(value) > MAX_LABELS:
            raise ValueError("Too many tags")
        results = []
        for record in value:
            if isinstance(record, str):
                results.append(_validate_label(record, 1.0))
            elif isinstance(record, dict):
                name = record.get("name", record.get("tag"))
                score = record.get("confidence", record.get("score", 1.0))
                results.append(_validate_label(name, score))
            else:
                raise ValueError("Unsupported tag entry")
        return tuple(results)
    raise ValueError("Unsupported tag response")


def _unwrap(payload):
    value = payload
    for _ in range(4):
        if not isinstance(value, dict):
            return value
        if "error" in value:
            raise ValueError("Tagger returned an error object")
        key = next((name for name in ("result", "data") if name in value and len(value) == 1), None)
        if key is None:
            return value
        value = value[key]
    return value


def _category_node(node):
    if not isinstance(node, dict):
        return node
    tags = node.get("tags")
    if isinstance(tags, dict) and any(
        key in tags for key in (
            "general", "general_tags", "character", "character_tags",
            "copyright", "copyright_tags", "rating", "ratings",
        )
    ):
        return tags
    return node


def _pick(node, names):
    if not isinstance(node, dict):
        return None
    for name in names:
        if name in node:
            return node[name]
    return None


def _filtered(entries, threshold):
    values = tuple(entry for entry in entries if entry.score >= threshold)
    if sum(len(entry.name) for entry in values) > MAX_LABEL_CHARS:
        raise ValueError("Tag result exceeds 16384 characters")
    return values


def parse_tag_result(payload, threshold, character_threshold, backend_id="auto_http", url="", model=""):
    node = _unwrap(payload)
    category = _category_node(node)

    if isinstance(category, dict):
        general_source = _pick(category, ("general", "general_tags"))
        if general_source is None:
            general_source = _pick(node, ("tag", "tags")) if isinstance(node, dict) else None
            if isinstance(general_source, dict) and any(
                key in general_source for key in ("general", "character", "rating", "copyright")
            ):
                general_source = _pick(general_source, ("general", "general_tags"))
        character_source = _pick(category, ("character", "characters", "character_tags"))
        copyright_source = _pick(category, ("copyright", "copyrights", "copyright_tags"))
        rating_source = _pick(category, ("rating", "ratings"))
        caption = _pick(node, ("caption",)) if isinstance(node, dict) else ""
    else:
        general_source = category
        character_source = copyright_source = rating_source = None
        caption = ""

    if general_source is None and isinstance(node, dict):
        direct_values = tuple(node.values())
        if node and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in direct_values
        ):
            general_source = node

    if isinstance(caption, str):
        if len(caption) > MAX_CAPTION:
            raise ValueError("Caption exceeds 8192 characters")
        caption = caption.strip()
        if general_source is None and "," in caption:
            general_source = caption
    elif caption is None:
        caption = ""
    else:
        raise ValueError("Caption must be a string")

    if (
        isinstance(node, dict)
        and node
        and general_source is None
        and character_source is None
        and copyright_source is None
        and rating_source is None
        and not caption
    ):
        raise ValueError("Unsupported tag response")

    general_all = _entries(general_source) if general_source is not None else ()
    character_all = _entries(character_source) if character_source is not None else ()
    copyright_all = _entries(copyright_source) if copyright_source is not None else ()
    rating_all = _entries(rating_source) if rating_source is not None else ()

    general = _filtered(general_all, threshold)
    characters = _filtered(character_all, character_threshold)
    copyrights = _filtered(copyright_all, threshold)
    rating = max(rating_all, key=lambda item: item.score).name if rating_all else ""

    backend = resolve_backend(backend_id, url).id if url else backend_id
    return NormalizedTagResult(
        content_tags=tuple(item.name for item in general),
        character_tags=tuple(item.name for item in characters),
        copyright_tags=tuple(item.name for item in copyrights),
        rating=rating,
        caption=caption,
        content_scores=general_all,
        character_scores=character_all,
        rating_scores=rating_all,
        backend=backend,
        model=model,
    )


def parse_tags(payload, threshold):
    """Compatibility helper used by existing tests/callers."""
    return parse_tag_result(payload, threshold, threshold).content_tags
