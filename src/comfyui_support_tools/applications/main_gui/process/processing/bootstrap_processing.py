from __future__ import annotations

from comfyui_support_tools.shared.contracts.application_models import (
    ApplicationConfig,
    ApplicationStatus,
)


def build_application_status(config: ApplicationConfig) -> ApplicationStatus:
    return ApplicationStatus(name=config.name, version=config.version, ready=True)
