from __future__ import annotations

from comfyui_support_tools.shared.contracts.application_models import ApplicationStatus


def format_status_text(status: ApplicationStatus) -> str:
    state = "ready" if status.ready else "not ready"
    return f"{status.name} {status.version}: {state}"
