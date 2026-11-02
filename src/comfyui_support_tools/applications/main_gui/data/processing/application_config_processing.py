from __future__ import annotations

import json
from pathlib import Path

from comfyui_support_tools.shared.contracts.application_models import ApplicationConfig


# {
#   責務: [load_application_config: UTF-8 JSONからapplication name/versionを読み込む]
#   処理: [JSON objectのname/versionをstring化し、未指定は製品名とversion 0を使う]
#   引数: [path: application config file]
#   戻り値: [ApplicationConfig: name/version contract]
#   エラー: [OSError/JSONDecodeError/AttributeError: fileまたはpayloadが読めない]
#   副作用: [config fileを読み取る]
# }
def load_application_config(path: Path) -> ApplicationConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ApplicationConfig(
        name=str(payload.get("name", "ComfyUI Support Tools")),
        version=str(payload.get("version", "0")),
    )
