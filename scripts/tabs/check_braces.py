from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

class CheckBracesTab(ttk.Frame):
    DEFAULT_DIR = str(WILDCARDS_DIR / "anime_character")
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
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"input_dir": self.input_dir.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")
    def load_preset(self):
        try:
            self.input_dir.set(self.preset_store.load(self.preset_name.get()).get("input_dir", self.input_dir.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")
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
    def run(self):
        import glob
        files=sorted(glob.glob(os.path.join(self.input_dir.get().strip(),"*.txt")))
        if not files: self.logbox.log("txtファイルが見つかりません"); return
        err=any(not self.check_file(f) for f in files)
        self.logbox.log("One or more files have unbalanced or premature braces." if err else "All files have balanced braces.")
