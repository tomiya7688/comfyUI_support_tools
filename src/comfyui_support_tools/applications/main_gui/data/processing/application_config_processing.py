from __future__ import annotations

import json
from pathlib import Path

from comfyui_support_tools.shared.contracts.application_models import ApplicationConfig


def load_application_config(path: Path) -> ApplicationConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ApplicationConfig(
        name=str(payload.get("name", "ComfyUI Support Tools")),
        version=str(payload.get("version", "0")),
    )
