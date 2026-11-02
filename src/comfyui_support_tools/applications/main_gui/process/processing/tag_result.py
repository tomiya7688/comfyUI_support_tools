"""Inspector compatibility exports for shared Tagger result normalization."""

from typing import Any

from comfyui_support_tools.shared.tag_result_normalizer import parse_tag_result


# {
#   責務: [parse_tags: Inspector compatibility contractのflat tags inputをshared normalizerへ委譲する]
#   処理: [legacy empty tags/style objectをempty扱いし、nested tag mappingをunwrapしてparseする]
#   引数: [payload: Tagger response, threshold: content/character minimum confidence]
#   戻り値: [tuple[str,...]: normalized content tags]
#   エラー: [ValueError: shared parserがpayload/thresholdを拒否した]
# }
def parse_tags(payload: Any, threshold: float) -> tuple[str, ...]:
    """Retain the older flat {"tag": {name: confidence}} API."""
    if (
        isinstance(payload, dict)
        and payload.get("tags") == []
        and set(payload).issubset({"tags", "style"})
    ):
        return ()
    if isinstance(payload, dict) and isinstance(payload.get("tag"), dict):
        payload = payload["tag"]
    return parse_tag_result(payload, threshold, threshold).content_tags
