from __future__ import annotations
import threading
from ..context import *
from ..backend.ollama_prompt_corrector import OllamaPromptCorrector
from ..services import LogBox
from ..widgets.preset_store import PresetStore

# {
#   "責務": "Ollama modelで自由文をprompt tagへ校正するUI。",
#   "フィールド": ["api_url: Ollama API endpoint", "model: 校正model", "preset_name/preset_store/preset_combo: 設定保存・選択", "source: 入力自由文", "result: 校正結果", "logbox: 操作状況"]
# }
class OllamaPromptTab(ttk.Frame):
    # {
    #   "責務": "API・model・presetの初期値を設定し校正画面を構築する。",
    #   "処理": ["Ollama endpointと空のmodel選択状態を作る", "preset保存先を初期化して各widgetを配置する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self,master):
        super().__init__(master,padding=10); self.api_url=tk.StringVar(value="http://127.0.0.1:11434"); self.model=tk.StringVar(); self.preset_name=tk.StringVar(); self.preset_store=PresetStore("ollama_prompt"); self._build()
    # {
    #   "責務": "API・model選択・自由文入力・結果・preset・log UIを作る。",
    #   "処理": ["endpointとmodel操作欄を配置する", "入力・実行・preset・出力・log widgetを構築する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        row=ttk.Frame(self); row.pack(fill="x",pady=3); ttk.Label(row,text="Ollama API",width=16).pack(side="left"); ttk.Entry(row,textvariable=self.api_url).pack(side="left",fill="x",expand=True); ttk.Button(row,text="モデル一覧",command=self.refresh_models).pack(side="left",padx=4)
        row=ttk.Frame(self); row.pack(fill="x",pady=3); ttk.Label(row,text="モデル",width=16).pack(side="left"); self.model_combo=ttk.Combobox(row,textvariable=self.model); self.model_combo.pack(side="left",fill="x",expand=True)
        ttk.Label(self,text="入力（日本語・自由文可）").pack(anchor="w",pady=(6,0)); self.source=tk.Text(self,height=7); self.source.pack(fill="both",expand=True)
        buttons=ttk.Frame(self); buttons.pack(fill="x",pady=6); ttk.Button(buttons,text="タグへ校正",command=self.start).pack(side="left"); ttk.Label(buttons,text="preset").pack(side="left",padx=(16,4)); self.preset_combo=ttk.Combobox(buttons,textvariable=self.preset_name,width=18); self.preset_combo.pack(side="left"); ttk.Button(buttons,text="保存",command=self.save_preset).pack(side="left",padx=4); ttk.Button(buttons,text="読込",command=self.load_preset).pack(side="left",padx=4)
        ttk.Label(self,text="出力").pack(anchor="w"); self.result=tk.Text(self,height=7); self.result.pack(fill="both",expand=True); self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True); self._refresh()
    # {
    #   "責務": "preset名一覧を選択UIへ反映する。",
    #   "処理": ["保存済み名前をcomboboxへ設定する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh(self): self.preset_combo.configure(values=self.preset_store.names())
    # {
    #   "責務": "Ollama model一覧の問い合わせをworker threadで開始する。",
    #   "処理": ["_refresh_modelsをdaemon threadで実行する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def refresh_models(self): threading.Thread(target=self._refresh_models,daemon=True).start()
    # {
    #   "責務": "APIからOllama model一覧を取得してcomboboxを更新する。",
    #   "処理": ["requests依存を確認する", "model一覧を取得しTk threadで選択肢と初期modelを設定する", "結果またはerrorをlogへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_models(self):
        try:
            if requests is None: raise RuntimeError("requests がありません")
            models=OllamaPromptCorrector().models(self.api_url.get(),requests); self.after(0,lambda:self.model_combo.configure(values=models));
            if models and not self.model.get(): self.after(0,lambda:self.model.set(models[0]))
            self.logbox.log(f"モデル一覧: {len(models)}件")
        except Exception as error:self.logbox.log(f"モデル一覧エラー: {error}")
    # {
    #   "責務": "prompt校正処理をdaemon threadで開始する。",
    #   "処理": ["runをworker threadで起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def start(self): threading.Thread(target=self.run,daemon=True).start()
    # {
    #   "責務": "入力文を選択modelで校正し結果widgetへ表示する。",
    #   "処理": ["requests依存を確認する", "OllamaPromptCorrectorへendpoint/model/入力文を渡す", "結果またはerrorを表示・記録する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        try:
            if requests is None: raise RuntimeError("requests がありません")
            result=OllamaPromptCorrector().correct(self.api_url.get(),self.model.get(),self.source.get("1.0","end"),requests); self.result.delete("1.0","end"); self.result.insert("end",result); self.logbox.log("校正完了")
        except Exception as error:self.logbox.log(f"校正エラー: {error}")
    # {
    #   "責務": "API endpoint・model・入力文をpresetとして保存する。",
    #   "処理": ["現在値を保存し選択名を更新する", "保存結果をlogへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        path=self.preset_store.save(self.preset_name.get(),{"api_url":self.api_url.get(),"model":self.model.get(),"source":self.source.get("1.0","end-1c")}); self.preset_name.set(path.stem); self._refresh(); self.logbox.log(f"プリセットを保存しました: {path}")
    # {
    #   "責務": "選択presetからendpoint・model・入力文を復元する。",
    #   "処理": ["保存値を各widgetへ反映する", "読込完了をlogへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        values=self.preset_store.load(self.preset_name.get()); self.api_url.set(values.get("api_url",self.api_url.get())); self.model.set(values.get("model",self.model.get())); self.source.delete("1.0","end"); self.source.insert("end",values.get("source","")); self.logbox.log("プリセットを読み込みました")
