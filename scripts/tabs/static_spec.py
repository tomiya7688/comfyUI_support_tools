from __future__ import annotations
import threading
from pathlib import Path
from ..context import *
from ..backend.static_spec_generator import StaticSpecGenerator
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore

class StaticSpecTab(ttk.Frame):
    def __init__(self,master):
        super().__init__(master,padding=10); self.target=tk.StringVar(); self.output=tk.StringVar(value=str(USER_DATA_DIR/"output"/"static_spec.md")); self.recursive=tk.BooleanVar(value=True); self.preset_name=tk.StringVar(); self.preset_store=PresetStore("static_spec"); self._build()
    def _build(self):
        row=ttk.Frame(self); row.pack(fill="x",pady=3); ttk.Label(row,text="Pythonファイル / フォルダ",width=22).pack(side="left"); ttk.Entry(row,textvariable=self.target).pack(side="left",fill="x",expand=True); ttk.Button(row,text="ファイル",command=lambda:self._choose(False)).pack(side="left",padx=3); ttk.Button(row,text="フォルダ",command=lambda:self._choose(True)).pack(side="left")
        LabeledPathRow(self,"出力Markdown",self.output,mode="save",filetypes=[("Markdown","*.md"),("All","*.*")]).pack(fill="x",pady=3); ttk.Checkbutton(self,text="サブフォルダも解析",variable=self.recursive).pack(anchor="w")
        buttons=ttk.Frame(self); buttons.pack(fill="x",pady=6); ttk.Button(buttons,text="仕様書を生成",command=self.start).pack(side="left",padx=4); ttk.Label(buttons,text="preset").pack(side="left",padx=(16,4)); self.preset_combo=ttk.Combobox(buttons,textvariable=self.preset_name,width=18); self.preset_combo.pack(side="left"); ttk.Button(buttons,text="保存",command=self.save_preset).pack(side="left",padx=4); ttk.Button(buttons,text="読込",command=self.load_preset).pack(side="left",padx=4)
        self.logbox=LogBox(self); self.logbox.pack(fill="both",expand=True); self._refresh()
    def _choose(self,folder):
        path=filedialog.askdirectory() if folder else filedialog.askopenfilename(filetypes=[("Python","*.py")])
        if path:self.target.set(path)
    def _refresh(self): self.preset_combo.configure(values=self.preset_store.names())
    def save_preset(self):
        path=self.preset_store.save(self.preset_name.get(),{"target":self.target.get(),"output":self.output.get(),"recursive":self.recursive.get()}); self.preset_name.set(path.stem); self._refresh(); self.logbox.log(f"プリセットを保存しました: {path}")
    def load_preset(self):
        values=self.preset_store.load(self.preset_name.get()); self.target.set(values.get("target",self.target.get())); self.output.set(values.get("output",self.output.get())); self.recursive.set(values.get("recursive",self.recursive.get())); self.logbox.log("プリセットを読み込みました")
    def start(self): threading.Thread(target=self.run,daemon=True).start()
    def run(self):
        try:
            target,output=Path(self.target.get().strip()),Path(self.output.get().strip())
            if not(target.is_file() or target.is_dir()): raise ValueError(f"対象がありません: {target}")
            count=StaticSpecGenerator().generate_files(target,output,self.recursive.get()); self.logbox.log(f"生成完了: {count}ファイル / {output}")
        except Exception as error:self.logbox.log(f"生成エラー: {error}")
