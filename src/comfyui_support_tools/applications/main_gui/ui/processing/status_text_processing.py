from __future__ import annotations

from comfyui_support_tools.shared.contracts.application_models import ApplicationStatus


# {
#   責務: [format_status_text: ApplicationStatusをshell向け短いstatus lineへ整形する]
#   処理: [name/versionの後へready flagに応じreadyまたはnot readyを付ける]
#   引数: [status: ApplicationStatus]
#   戻り値: [str: formatted status text]
# }
def format_status_text(status: ApplicationStatus) -> str:
    state = "ready" if status.ready else "not ready"
    return f"{status.name} {status.version}: {state}"
