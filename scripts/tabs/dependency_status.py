from __future__ import annotations
import threading
from ..context import *
from ..backend.dependency_checker import DependencyChecker
from ..services import LogBox

# {
#   "責務": "アプリが利用するフォルダ・外部コマンド・任意APIの状態を確認するUI。",
#   "フィールド": ["api_check: API疎通検査を行うか", "logbox: 検査結果表示"]
# }
class DependencyStatusTab(ttk.Frame):
    # {
    #   "責務": "依存状態画面を初期化して構築する。",
    #   "処理": ["API検査設定を初期化する", "依存状態確認UIを構築する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self,master):
        super().__init__(master,padding=10); self.api_check=tk.BooleanVar(value=False); self._build()
    # {
    #   "責務": "依存状態の実行操作と結果表示を配置する。",
    #   "処理": ["API検査用checkboxと状態確認buttonを配置する", "ログ領域を作る"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        ttk.Label(self,text="依存状態（確認のみ。未導入でも他タブは利用できます）").pack(anchor="w")
        buttons=ttk.Frame(self); buttons.pack(fill="x",pady=6); ttk.Checkbutton(buttons,text="ローカルAPIの疎通も確認",variable=self.api_check).pack(side="left"); ttk.Button(buttons,text="状態を確認",command=self.start).pack(side="left",padx=8)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True)
    # {
    #   "責務": "依存検査をdaemon threadで開始する。",
    #   "処理": ["runをworker threadで起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def start(self): threading.Thread(target=self.run,daemon=True).start()
    # {
    #   "責務": "設定済みのパス・コマンドと選択時のAPIを検査してログへ報告する。",
    #   "処理": ["DependencyCheckerで存在・PATH・HTTP応答を確認する", "各結果と詳細をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        checker=DependencyChecker(); paths={"WebUI1111":A1111_DIR,"ComfyUI":COMFYUI_DIR,"PixAI Tagger":PIXAI_TAGGER_DIR,"共有models":MODELS_DIR,"wildcards":WILDCARDS_DIR}
        for label,ok in checker.check_paths(paths).items(): self.logbox.log(("✅ " if ok else "⚠️ ")+label+(" 利用可能" if ok else " 見つかりません"))
        for label,ok in checker.check_commands().items(): self.logbox.log(("✅ " if ok else "⚠️ ")+label+(" 利用可能" if ok else " PATHにありません"))
        if self.api_check.get():
            for label,url in (("WebUI1111 API",str(USER_PATHS.get("webui_api_url","http://127.0.0.1:7860"))+"/sdapi/v1/options"),("ComfyUI API",str(USER_PATHS.get("comfyui_api_url","http://127.0.0.1:8188"))+"/system_stats"),("PixAI API",PIXAI_TAGGER_API_URL)):
                ok,detail=checker.check_api(url,requests); self.logbox.log(("✅ " if ok else "⚠️ ")+f"{label}: {detail}")
