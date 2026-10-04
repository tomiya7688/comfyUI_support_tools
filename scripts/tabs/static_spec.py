from __future__ import annotations
import threading
from pathlib import Path
from ..context import *
from ..backend.static_spec_generator import StaticSpecGenerator
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore

# {
#   "責務": "Pythonソースから静的な仕様Markdownを生成するUI。",
#   "フィールド": ["target: 解析対象", "output: 生成先", "recursive: 子folder走査設定", "preset_name: プリセット選択名", "preset_store: プリセット保存先", "logbox: 実行結果表示"]
# }
class StaticSpecTab(ttk.Frame):
    # {
    #   "責務": "対象・出力・再帰設定を初期化して仕様生成画面を組み立てる。",
    #   "処理": ["pathとpreset状態を設定する", "入力・出力・実行・ログUIを配置する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self,master):
        super().__init__(master,padding=10); self.target=tk.StringVar(); self.output=tk.StringVar(value=str(USER_DATA_DIR/"output"/"static_spec.md")); self.recursive=tk.BooleanVar(value=True); self.preset_name=tk.StringVar(); self.preset_store=PresetStore("static_spec"); self._build()
    # {
    #   "責務": "Python対象・Markdown出力先・再帰走査を設定するUIを作る。",
    #   "処理": ["file/folder選択と出力先入力を配置する", "再帰・実行・preset操作とlog領域を配置する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        row=ttk.Frame(self); row.pack(fill="x",pady=3); ttk.Label(row,text="Pythonファイル / フォルダ",width=22).pack(side="left"); ttk.Entry(row,textvariable=self.target).pack(side="left",fill="x",expand=True); ttk.Button(row,text="ファイル",command=lambda:self._choose(False)).pack(side="left",padx=3); ttk.Button(row,text="フォルダ",command=lambda:self._choose(True)).pack(side="left")
        LabeledPathRow(self,"出力Markdown",self.output,mode="save",filetypes=[("Markdown","*.md"),("All","*.*")]).pack(fill="x",pady=3); ttk.Checkbutton(self,text="サブフォルダも解析",variable=self.recursive).pack(anchor="w")
        buttons=ttk.Frame(self); buttons.pack(fill="x",pady=6); ttk.Button(buttons,text="仕様書を生成",command=self.start).pack(side="left",padx=4); ttk.Label(buttons,text="preset").pack(side="left",padx=(16,4)); self.preset_combo=ttk.Combobox(buttons,textvariable=self.preset_name,width=18); self.preset_combo.pack(side="left"); ttk.Button(buttons,text="保存",command=self.save_preset).pack(side="left",padx=4); ttk.Button(buttons,text="読込",command=self.load_preset).pack(side="left",padx=4)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True); self._refresh()
    # {
    #   "責務": "解析対象としてPython fileかfolderを選択する。",
    #   "処理": ["folderに応じたdialogを開く", "選択されたpathがある場合targetへ設定する"],
    #   "引数": {"folder": "Trueならfolder、FalseならPython fileを選択"},
    #   "戻り値": []
    # }
    def _choose(self,folder):
        path=filedialog.askdirectory() if folder else filedialog.askopenfilename(filetypes=[("Python","*.py")])
        if path:self.target.set(path)
    # {
    #   "責務": "保存済みpreset名を選択UIへ反映する。",
    #   "処理": ["PresetStoreの名前一覧を取得して選択肢を更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh(self): self.preset_combo.configure(values=self.preset_store.names())
    # {
    #   "責務": "解析対象・出力先・再帰設定をpresetへ保存する。",
    #   "処理": ["現在値を保存し表示名と選択肢を更新する", "保存先をログへ報告する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        path=self.preset_store.save(self.preset_name.get(),{"target":self.target.get(),"output":self.output.get(),"recursive":self.recursive.get()}); self.preset_name.set(path.stem); self._refresh(); self.logbox.log(f"プリセットを保存しました: {path}")
    # {
    #   "責務": "選択presetから解析対象・出力先・再帰設定を復元する。",
    #   "処理": ["保存値を各Tk変数へ反映する", "読込完了をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        values=self.preset_store.load(self.preset_name.get()); self.target.set(values.get("target",self.target.get())); self.output.set(values.get("output",self.output.get())); self.recursive.set(values.get("recursive",self.recursive.get())); self.logbox.log("プリセットを読み込みました")
    # {
    #   "責務": "仕様書生成処理をdaemon threadで開始する。",
    #   "処理": ["runをworker threadへ渡して起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def start(self): threading.Thread(target=self.run,daemon=True).start()
    # {
    #   "責務": "対象ソースを解析して仕様Markdownを出力する。",
    #   "処理": ["対象と出力pathを検証する", "StaticSpecGeneratorへ再帰設定とともに処理を委譲する", "成否をログへ報告する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        try:
            target,output=Path(self.target.get().strip()),Path(self.output.get().strip())
            if not(target.is_file() or target.is_dir()): raise ValueError(f"対象がありません: {target}")
            count=StaticSpecGenerator().generate_files(target,output,self.recursive.get()); self.logbox.log(f"生成完了: {count}ファイル / {output}")
        except Exception as error:self.logbox.log(f"生成エラー: {error}")
