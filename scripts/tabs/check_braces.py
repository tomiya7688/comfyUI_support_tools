from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

# {
#   "責務": "ワイルドカードtxtの括弧バランス確認UIとプリセットを管理する。",
#   "フィールド": ["DEFAULT_DIR: 初期検査先", "input_dir: 検査先", "preset_store: プリセット保存先", "preset_name: 選択プリセット名", "preset_combo: 選択肢UI", "logbox: 検査結果表示"]
# }
class CheckBracesTab(ttk.Frame):
    DEFAULT_DIR = str(WILDCARDS_DIR / "anime_character")
    # {
    #   "責務": "検査画面と初期状態を組み立てる。",
    #   "処理": ["親widgetへ検査先・プリセット操作・ログ表示を配置する", "保存済みプリセット名を表示する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master,padding=10); self.input_dir=tk.StringVar(value=self.DEFAULT_DIR)
        self.preset_store = PresetStore("check_braces"); self.preset_name = tk.StringVar()
        LabeledPathRow(self,"input_dir",self.input_dir,mode="dir").pack(fill="x",pady=4)
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=8)
        ttk.Button(buttons,text="{} バランス確認",command=lambda:_safe_thread(self.logbox,self.run)).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True); self._refresh_preset_choices()
    # {
    #   "責務": "保存済みプリセットを選択UIへ反映する。",
    #   "処理": ["PresetStoreから名前一覧を取得しcomboboxへ設定する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())
    # {
    #   "責務": "検査先を名前付きプリセットとして保存する。",
    #   "処理": ["現在の検査先を保存する", "保存名と選択肢を更新し結果をログへ出す", "保存失敗をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"input_dir": self.input_dir.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")
    # {
    #   "責務": "選択プリセットの検査先を画面へ復元する。",
    #   "処理": ["保存済み検査先を読み込み現在値へ反映する", "成功または失敗をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            self.input_dir.set(self.preset_store.load(self.preset_name.get()).get("input_dir", self.input_dir.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")
    # {
    #   "責務": "1つのテキストファイルで波括弧の開閉が釣り合うか調べる。",
    #   "処理": ["行ごとに括弧数を加減する", "途中で閉じ過ぎまたは最終不一致を検出したらログへ出す"],
    #   "引数": {"path": "検査対象ファイル"},
    #   "戻り値": "全体の括弧が釣り合えばTrue、それ以外はFalse"
    # }
    def check_file(self,path):
        bal=0
        with open(path,"r",encoding="utf-8") as f:
            for no,line in enumerate(f,1):
                for ch in line:
                    if ch=="{": bal+=1
                    elif ch=="}":
                        bal-=1
                        if bal<0: self.logbox.log(f"[ERROR] Too many closing braces in {path} at line {no}"); return False
        if bal!=0: self.logbox.log(f"[ERROR] Unbalanced braces in {path}: final balance = {bal}"); return False
        return True
    # {
    #   "責務": "指定フォルダ直下のtxtファイルを一括検査する。",
    #   "処理": ["対象一覧を作り各ファイルをcheck_fileへ渡す", "不一致の有無をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        import glob
        files=sorted(glob.glob(os.path.join(self.input_dir.get().strip(),"*.txt")))
        if not files: self.logbox.log("txtファイルが見つかりません"); return
        err=any(not self.check_file(f) for f in files)
        self.logbox.log("One or more files have unbalanced or premature braces." if err else "All files have balanced braces.")
