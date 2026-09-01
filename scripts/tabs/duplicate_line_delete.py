from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

class DuplicateLineDeleteTab(ttk.Frame):
    DEFAULT_FILE = str(WILDCARDS_DIR / "anime_character_name.txt")
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
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"target_file": self.target_file.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")
    def load_preset(self):
        try:
            self.target_file.set(self.preset_store.load(self.preset_name.get()).get("target_file", self.target_file.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")
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
