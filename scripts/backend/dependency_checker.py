from __future__ import annotations
import shutil
from pathlib import Path

class DependencyChecker:
    """ローカル依存関係と任意APIの利用可否を検査する。"""
    def check_paths(self, paths: dict[str, Path]) -> dict[str, bool]:
        return {label: path.exists() for label,path in paths.items()}
    def check_commands(self) -> dict[str, bool]:
        return {name: shutil.which(name) is not None for name in ("ffmpeg","ffprobe")}
    def check_api(self, url: str, requests_module) -> tuple[bool,str]:
        if requests_module is None: return False,"requests未導入"
        try:
            response=requests_module.get(url,timeout=3); return response.ok,f"HTTP {response.status_code}"
        except Exception as error: return False,type(error).__name__
