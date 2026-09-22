"""Parse supported content-tag formats without merging Style into Tags."""
import math


def parse_tags(payload, threshold):
    value = payload
    for _ in range(4):
        if not isinstance(value, dict):
            break
        if "error" in value:
            raise ValueError("Tagger returned an error object")
        key = next((key for key in ("tag", "tags", "caption") if key in value), None)
        if key is None:
            break
        value = value[key]
    if isinstance(value, str):
        entries = [(name.strip(), 1.0) for name in value.split(",") if name.strip()]
    elif isinstance(value, dict):
        entries = list(value.items())
    elif isinstance(value, list):
        entries = []
        for record in value:
            if isinstance(record, str):
                entries.append((record, 1.0))
            elif isinstance(record, dict):
                entries.append((record.get("name", record.get("tag")), record.get("confidence", record.get("score", 1.0))))
            else:
                raise ValueError("Unsupported tag entry")
    else:
        raise ValueError("Unsupported tag response")
    if len(entries) > 2000:
        raise ValueError("Too many tags")
    tags = []
    for name, score in entries:
        if (not isinstance(name, str) or not name.strip() or len(name) > 256
                or any(ord(c) < 32 for c in name) or isinstance(score, bool)
                or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError("Invalid tag name or confidence")
        if score >= threshold:
            tags.append(name.strip())
    if sum(map(len, tags)) > 16384:
        raise ValueError("Tag result exceeds 16384 characters")
    return tuple(dict.fromkeys(tags))
