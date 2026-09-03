from __future__ import annotations
import threading
from ..context import *
from ..backend.ollama_prompt_corrector import OllamaPromptCorrector
from ..services import LogBox
from ..widgets.preset_store import PresetStore

class OllamaPromptTab(ttk.Frame):
    def __init__(self,master):
        super().__init__(master,padding=10); self.api_url=tk.StringVar(value="http://127.0.0.1:11434"); self.model=tk.StringVar(); self.preset_name=tk.StringVar(); self.preset_store=PresetStore("ollama_prompt"); self._build()
    def _build(self):
        row=ttk.Frame(self); row.pack(fill="x",pady=3); ttk.Label(row,text="Ollama API",width=16).pack(side="left"); ttk.Entry(row,textvariable=self.api_url).pack(side="left",fill="x",expand=True); ttk.Button(row,text="モデル一覧",command=self.refresh_models).pack(side="left",padx=4)
        row=ttk.Frame(self); row.pack(fill="x",pady=3); ttk.Label(row,text="モデル",width=16).pack(side="left"); self.model_combo=ttk.Combobox(row,textvariable=self.model); self.model_combo.pack(side="left",fill="x",expand=True)
        ttk.Label(self,text="入力（日本語・自由文可）").pack(anchor="w",pady=(6,0)); self.source=tk.Text(self,height=7); self.source.pack(fill="both",expand=True)
        buttons=ttk.Frame(self); buttons.pack(fill="x",pady=6); ttk.Button(buttons,text="タグへ校正",command=self.start).pack(side="left"); ttk.Label(buttons,text="preset").pack(side="left",padx=(16,4)); self.preset_combo=ttk.Combobox(buttons,textvariable=self.preset_name,width=18); self.preset_combo.pack(side="left"); ttk.Button(buttons,text="保存",command=self.save_preset).pack(side="left",padx=4); ttk.Button(buttons,text="読込",command=self.load_preset).pack(side="left",padx=4)
        ttk.Label(self,text="出力").pack(anchor="w"); self.result=tk.Text(self,height=7); self.result.pack(fill="both",expand=True); self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True); self._refresh()
    def _refresh(self): self.preset_combo.configure(values=self.preset_store.names())
    def refresh_models(self): threading.Thread(target=self._refresh_models,daemon=True).start()
    def _refresh_models(self):
        try:
            if requests is None: raise RuntimeError("requests がありません")
            models=OllamaPromptCorrector().models(self.api_url.get(),requests); self.after(0,lambda:self.model_combo.configure(values=models));
            if models and not self.model.get(): self.after(0,lambda:self.model.set(models[0]))
            self.logbox.log(f"モデル一覧: {len(models)}件")
        except Exception as error:self.logbox.log(f"モデル一覧エラー: {error}")
    def start(self): threading.Thread(target=self.run,daemon=True).start()
    def run(self):
        try:
            if requests is None: raise RuntimeError("requests がありません")
            result=OllamaPromptCorrector().correct(self.api_url.get(),self.model.get(),self.source.get("1.0","end"),requests); self.result.delete("1.0","end"); self.result.insert("end",result); self.logbox.log("校正完了")
        except Exception as error:self.logbox.log(f"校正エラー: {error}")
    def save_preset(self):
        path=self.preset_store.save(self.preset_name.get(),{"api_url":self.api_url.get(),"model":self.model.get(),"source":self.source.get("1.0","end-1c")}); self.preset_name.set(path.stem); self._refresh(); self.logbox.log(f"プリセットを保存しました: {path}")
    def load_preset(self):
        values=self.preset_store.load(self.preset_name.get()); self.api_url.set(values.get("api_url",self.api_url.get())); self.model.set(values.get("model",self.model.get())); self.source.delete("1.0","end"); self.source.insert("end",values.get("source","")); self.logbox.log("プリセットを読み込みました")
