from __future__ import annotations

from comfyui_support_tools.shared.contracts.application_models import (
    ApplicationConfig,
    ApplicationStatus,
)


# {
#   責務: [build_application_status: ApplicationConfigをready status contractへ投影する]
#   処理: [name/versionを保ちready=TrueのApplicationStatusを作る]
#   引数: [config: 読み込んだApplicationConfig]
#   戻り値: [ApplicationStatus: config identityとready flag]
# }
def build_application_status(config: ApplicationConfig) -> ApplicationStatus:
    return ApplicationStatus(name=config.name, version=config.version, ready=True)
