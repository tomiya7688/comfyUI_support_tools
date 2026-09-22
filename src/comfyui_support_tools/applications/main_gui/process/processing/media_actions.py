"""GUI-independent action discovery and validation; no backend execution here."""
import math
from urllib.parse import urlsplit

from comfyui_support_tools.shared.contracts.inspector_contracts import (
    ActionAvailability, ActionDefinition, TaggerSettings,
)

# EXTENSION_POINT: add explicit supported kinds and an API adapter together.
# Do not turn a placeholder on until its handler exists. See doc/gui/inspector_actions.md.
ACTIONS = (
    ActionDefinition("tag", "Tag / 内容タグ付け", ("image",)),
    ActionDefinition("style", "Analyze Style", ("image",), "Style Analyzer API adapter未実装"),
    ActionDefinition("img2img", "Img2img", ("image",), "生成Action adapter未実装"),
    ActionDefinition("dataset", "Add to LoRA Dataset", ("image",), "Dataset登録Action未実装"),
    ActionDefinition("character", "Character Replace", ("image",), "Character API adapter未実装"),
    ActionDefinition("variations", "Generate Variations", ("image",), "生成Action adapter未実装"),
    ActionDefinition("video", "Video Actions", ("video",), "動画Action adapter未実装"),
)


def validate_settings(settings: TaggerSettings) -> None:
    url = settings.url
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("API URLのportが不正です") from exc
    if (parts.scheme not in ("http", "https") or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or any(c.isspace() for c in url)
            or not parts.path.endswith(("/pixai/v1/interrogate", "/tagger/v1/interrogate"))
            or len(url) > 2048 or (port is not None and not 1 <= port <= 65535)):
        raise ValueError("HTTP(S)の /pixai/v1/interrogate または /tagger/v1/interrogate URLを指定してください（認証情報・query不可）")
    if len(settings.model) > 256 or any(ord(c) < 32 for c in settings.model):
        raise ValueError("モデル名が不正です")
    for number in (settings.threshold, settings.character_threshold):
        if isinstance(number, bool) or not math.isfinite(number) or not 0 <= number <= 1:
            raise ValueError("閾値は0〜1の有限数で指定してください")
    if not math.isfinite(settings.timeout) or not 1 <= settings.timeout <= 120:
        raise ValueError("timeoutは1〜120秒で指定してください")


def action_options(items, ready: bool, busy: bool):
    results = []
    for action in ACTIONS:
        reason = action.unavailable
        if not reason and not items:
            reason = "メディアを選択してください"
        if not reason and (len(items) > 60 or any(item.kind not in action.kinds for item in items)):
            reason = "画像のみを1〜60件選択してください（混在選択は不可）"
        if not reason and busy:
            reason = "Action実行中です。終了または停止を待ってください"
        if not reason and not ready:
            reason = "Tagger API未確認・未接続。API設定から接続確認してください"
        results.append(ActionAvailability(action, not reason, reason))
    return tuple(results)
