"""Inspector compatibility exports for shared Tagger result normalization."""

from typing import Any

from comfyui_support_tools.shared.tag_result_normalizer import parse_tag_result


def parse_tags(payload: Any, threshold: float) -> tuple[str, ...]:
    """Retain the older flat {"tag": {name: confidence}} API."""
    if isinstance(payload, dict) and payload.get("tags") == [] and set(payload).issubset({"tags", "style"}):
        return ()
    if isinstance(payload, dict) and isinstance(payload.get("tag"), dict):
        payload = payload["tag"]
    return parse_tag_result(payload, threshold, threshold).content_tags
