from __future__ import annotations
import threading
from ..context import *
from ..backend.dependency_checker import DependencyChecker
from ..services import LogBox

class DependencyStatusTab(ttk.Frame):
    def __init__(self,master):
        super().__init__(master,padding=10); self.api_check=tk.BooleanVar(value=False); self._build()
    def _build(self):
        ttk.Label(self,text="依存状態（確認のみ。未導入でも他タブは利用できます）").pack(anchor="w")
        buttons=ttk.Frame(self); buttons.pack(fill="x",pady=6); ttk.Checkbutton(buttons,text="ローカルAPIの疎通も確認",variable=self.api_check).pack(side="left"); ttk.Button(buttons,text="状態を確認",command=self.start).pack(side="left",padx=8)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True)
    def start(self): threading.Thread(target=self.run,daemon=True).start()
    def run(self):
        checker=DependencyChecker(); paths={"WebUI1111":A1111_DIR,"ComfyUI":COMFYUI_DIR,"PixAI Tagger":PIXAI_TAGGER_DIR,"共有models":MODELS_DIR,"wildcards":WILDCARDS_DIR}
        for label,ok in checker.check_paths(paths).items(): self.logbox.log(("✅ " if ok else "⚠️ ")+label+(" 利用可能" if ok else " 見つかりません"))
        for label,ok in checker.check_commands().items(): self.logbox.log(("✅ " if ok else "⚠️ ")+label+(" 利用可能" if ok else " PATHにありません"))
        if self.api_check.get():
            for label,url in (("WebUI1111 API",str(USER_PATHS.get("webui_api_url","http://127.0.0.1:7860"))+"/sdapi/v1/options"),("ComfyUI API",str(USER_PATHS.get("comfyui_api_url","http://127.0.0.1:8188"))+"/system_stats"),("PixAI API",PIXAI_TAGGER_API_URL)):
                ok,detail=checker.check_api(url,requests); self.logbox.log(("✅ " if ok else "⚠️ ")+f"{label}: {detail}")
