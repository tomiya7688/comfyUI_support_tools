from __future__ import annotations

import threading
from pathlib import Path

from ..context import *
from ..backend.tag_category_splitter import TagCategorySplitter
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore


class TagSplitterTab(ttk.Frame):
    """タグtxtを用途別のフォルダ群へ複製して分割する画面。"""

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(USER_DATA_DIR / "output" / "tag_splitter"))
        self.recursive = tk.BooleanVar(value=True)
        self.preset_name = tk.StringVar()
        self.preset_store = PresetStore("tag_splitter")
        self._build()

    def _build(self):
        LabeledPathRow(self, "入力タグフォルダ", self.input_dir, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(self, "出力先", self.output_dir, mode="dir").pack(fill="x", pady=3)
        ttk.Checkbutton(self, text="サブフォルダも処理", variable=self.recursive).pack(anchor="w", pady=4)
        ttk.Label(self, text="カテゴリ: 人物 / ポーズ / 服 / 画風 / 背景 / 状況 / 表情 と、それらの複合5種類").pack(anchor="w", pady=(2, 8))
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=4)
        ttk.Button(buttons, text="分割開始", command=self.start).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"input_dir": self.input_dir.get(), "output_dir": self.output_dir.get(), "recursive": self.recursive.get()})
            self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.input_dir.set(values.get("input_dir", self.input_dir.get())); self.output_dir.set(values.get("output_dir", self.output_dir.get())); self.recursive.set(values.get("recursive", self.recursive.get()))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        input_root = Path(self.input_dir.get().strip())
        output_root = Path(self.output_dir.get().strip())
        if not input_root.is_dir():
            self.logbox.log(f"入力タグフォルダがありません: {input_root}")
            return
        files = input_root.rglob("*.txt") if self.recursive.get() else input_root.glob("*.txt")
        files = sorted((path for path in files if path.is_file()), key=lambda path: path.as_posix().casefold())
        if not files:
            self.logbox.log("処理対象のtxtがありません")
            return
        splitter = TagCategorySplitter()
        self.logbox.log(f"分割開始: {len(files)}ファイル")
        for source in files:
            splitter.process_file(source, input_root, output_root)
            self.logbox.log(f"✅ {source.relative_to(input_root)}")
        self.logbox.log(f"完了: {output_root} / カテゴリ {len(splitter.CATEGORIES)}種類")
