from ..context import *
from ..context import _safe_thread
from ..services import *

class GenericSubprocessTab(ttk.Frame):
    """外部pyを単体GUIとして起動するタブ。random_line_picker.py等を単体で残したい用途にも使える。"""
    def __init__(self, master, title: str, script_name: str):
        super().__init__(master, padding=10)
        self.script_name = script_name
        ttk.Label(self, text=f"{script_name} は単体GUI/単体スクリプトとして起動します。").pack(anchor="w", pady=4)
        ttk.Button(self, text=f"{title} を別ウィンドウで起動", command=self.run).pack(fill="x", pady=8)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    def run(self):
        def _run():
            path = APP_DIR / self.script_name
            if not path.exists():
                self.logbox.log(f"見つかりません: {path}")
                return
            try:
                subprocess.Popen([sys.executable, str(path)], cwd=str(APP_DIR))
                self.logbox.log(f"起動しました: {path}")
            except Exception as e:
                self.logbox.log(f"起動エラー: {e}")
        _safe_thread(self.logbox, _run)
