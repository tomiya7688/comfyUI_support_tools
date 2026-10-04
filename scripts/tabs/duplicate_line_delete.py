from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

# {
#   "責務": "選択したテキストファイルから重複行を除去するUI。",
#   "フィールド": ["DEFAULT_FILE: 初期対象ファイル", "target_file: 対象パス", "preset_store: プリセット保存先", "preset_name: 選択プリセット名", "preset_combo: 選択肢UI", "logbox: 実行結果表示"]
# }
class DuplicateLineDeleteTab(ttk.Frame):
    DEFAULT_FILE = str(WILDCARDS_DIR / "anime_character_name.txt")
    # {
    #   "責務": "対象ファイル・プリセット操作・ログ領域を初期化する。",
    #   "処理": ["初期対象とプリセット状態を設定する", "パス欄・操作button・ログ領域を配置する", "保存済みプリセット一覧を反映する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.target_file=tk.StringVar(value=self.DEFAULT_FILE)
        self.preset_store = PresetStore("duplicate_line_delete")
        self.preset_name = tk.StringVar()
        LabeledPathRow(self,"対象txt",self.target_file,mode="file",filetypes=[("Text files","*.txt"),("All files","*.*")]).pack(fill="x",pady=4)
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=8)
        ttk.Button(buttons,text="重複行を削除",command=lambda:_safe_thread(self.logbox,self.run)).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True); self._refresh_preset_choices()
    # {
    #   "責務": "保存済みプリセット名をcomboboxへ反映する。",
    #   "処理": ["PresetStoreから名前を取得し選択肢へ設定する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())
    # {
    #   "責務": "現在の対象ファイルをプリセットへ保存する。",
    #   "処理": ["対象パスを保存し名前・選択肢を更新する", "成功または失敗をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"target_file": self.target_file.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")
    # {
    #   "責務": "選択したプリセットから対象ファイルを復元する。",
    #   "処理": ["プリセット値を読み対象パスへ反映する", "成否をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            self.target_file.set(self.preset_store.load(self.preset_name.get()).get("target_file", self.target_file.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")
    # {
    #   "責務": "対象ファイルの行順を保ち、完全一致する重複行を除いて上書きする。",
    #   "処理": ["入力ファイルの存在を確認する", "初出行を保持して同一ファイルへ書き戻す", "処理前後と削除数をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        path=self.target_file.get().strip()
        if not os.path.isfile(path): self.logbox.log(f"ファイルが存在しません: {path}"); return
        lines=Path(path).read_text(encoding="utf-8").splitlines(True)
        seen=set(); unique=[]
        for line in lines:
            if line not in seen: seen.add(line); unique.append(line)
        Path(path).write_text("".join(unique),encoding="utf-8")
        self.logbox.log(f"元の行数: {len(lines)}")
        self.logbox.log(f"削除された行数: {len(lines)-len(unique)}")
        self.logbox.log(f"新しい行数: {len(unique)}")
        self.logbox.log("完了しました")
