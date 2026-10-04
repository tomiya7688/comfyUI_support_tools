from pathlib import Path

from ..context import *
from ..context import _safe_thread
from ..services import *
from ..subapp_runtime import launch_packaged_executable, packaged_executable


# {
#   "責務": "同梱された別アプリを実行ファイル/API境界経由で起動するタブ。",
#   "フィールド": ["app_name: script_nameから解決した同梱アプリ名", "logbox: 起動結果表示"]
# }
class GenericSubprocessTab(ttk.Frame):
    """Packaged sub-app launcher. Cross-app integration is executable/API only."""

    # {
    #   "責務": "サブアプリ名を解決し起動操作とログUIを作る。",
    #   "処理": ["script_nameからapp_nameを決める", "起動説明・button・log領域を配置する"],
    #   "引数": {"master": "親Tk widget", "title": "起動buttonに表示する機能名", "script_name": "起動対象サブアプリのscript識別名"},
    #   "戻り値": []
    # }
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

    # {
    #   "責務": "登録済み同梱実行ファイルを別ウィンドウで起動する。",
    #   "処理": ["パッケージ内実行ファイルを解決する", "未導入・起動成功・起動例外をログへ報告する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        # {
        #   "責務": "実行ファイルの存在を確認してサブアプリを起動する。",
        #   "処理": ["アプリ実行ファイルを解決する", "未導入時の案内または起動結果をログへ出す"],
        #   "引数": [],
        #   "戻り値": []
        # }
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
