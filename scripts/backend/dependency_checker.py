from __future__ import annotations
import shutil
from pathlib import Path

# {
#   責務: [DependencyChecker: configured local paths, commands, and optional APIsのavailabilityをcheckする]
#   処理: [provide read-only dependency probes for the GUI]
#   フィールド: [stateless filesystem, command, and API probes]
# }
class DependencyChecker:
    """ローカル依存関係と任意APIの利用可否を検査する。"""
    # {
    #   責務: [check_paths: named filesystem pathsのexistence mappingを返す]
    #   処理: [test each Path.exists without modifying files]
    #   引数: [paths]
    #   戻り値: [dict[str, bool]]
    # }
    def check_paths(self, paths: dict[str, Path]) -> dict[str, bool]:
        return {label: path.exists() for label,path in paths.items()}
    # {
    #   責務: [check_commands: ffmpeg and ffprobeのPATH availabilityを返す]
    #   処理: [query shutil.which for supported commands]
    #   引数: [なし]
    #   戻り値: [dict[str, bool]]
    # }
    def check_commands(self) -> dict[str, bool]:
        return {name: shutil.which(name) is not None for name in ("ffmpeg","ffprobe")}
    # {
    #   責務: [check_api: optional requests clientでAPI endpoint healthをcheckする]
    #   処理: [return missing-client state or GET status and exception type]
    #   引数: [url, requests_module]
    #   戻り値: [tuple[bool, str]]
    # }
    def check_api(self, url: str, requests_module) -> tuple[bool,str]:
        if requests_module is None: return False,"requests未導入"
        try:
            response=requests_module.get(url,timeout=3); return response.ok,f"HTTP {response.status_code}"
        except Exception as error: return False,type(error).__name__
