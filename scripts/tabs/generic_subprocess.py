from pathlib import Path

from ..context import *
from ..context import _safe_thread
from ..services import *
from ..subapp_runtime import launch_packaged_executable, packaged_executable


class GenericSubprocessTab(ttk.Frame):
    """Packaged sub-app launcher. Cross-app integration is executable/API only."""

    def __init__(self, master, title: str, script_name: str):
        super().__init__(master, padding=10)
        self.app_name = Path(script_name).stem
        ttk.Label(
            self,
            text=f"{self.app_name} は独立した同梱アプリとして起動します。",
        ).pack(anchor="w", pady=4)
        ttk.Button(self, text=f"{title} を別ウィンドウで起動", command=self.run).pack(fill="x", pady=8)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    def run(self):
        def _run():
            executable = packaged_executable(self.app_name)
            if not executable.is_file():
                self.logbox.log(f"サブアプリが未導入です: {executable}")
                return
            try:
                launch_packaged_executable(executable)
                self.logbox.log(f"起動しました: {executable}")
            except Exception as e:
                self.logbox.log(f"起動エラー: {e}")
        _safe_thread(self.logbox, _run)
