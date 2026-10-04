from __future__ import annotations

import threading
from pathlib import Path

from ..context import *
from ..backend.tag_category_splitter import TagCategorySplitter
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore


# {
#   "責務": "tag txtを入力folderから読み分類カテゴリ別の出力へ分割するUI。",
#   "フィールド": ["input_dir: source folder", "output_dir: 分類出力folder", "recursive: 子folder走査設定", "preset_name/preset_store/preset_combo: 設定保存と選択", "logbox: 実行ログ"]
# }
class TagSplitterTab(ttk.Frame):
    """タグtxtを用途別のフォルダ群へ複製して分割する画面。"""

    # {
    #   "責務": "入出力先と走査設定を初期化し分類画面を構築する。",
    #   "処理": ["folder・再帰・preset stateを初期化する", "path・カテゴリ説明・実行・log UIを配置する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(USER_DATA_DIR / "output" / "tag_splitter"))
        self.recursive = tk.BooleanVar(value=True)
        self.preset_name = tk.StringVar()
        self.preset_store = PresetStore("tag_splitter")
        self._build()

    # {
    #   "責務": "入力・出力folderと再帰・preset・実行log UIを構築する。",
    #   "処理": ["pathと再帰設定を入力可能にする", "カテゴリ説明・操作button・log領域を配置する"],
    #   "引数": [],
    #   "戻り値": []
    # }
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

    # {
    #   "責務": "保存済みpreset一覧をcomboboxへ反映する。",
    #   "処理": ["PresetStoreから名前を読み選択肢を更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "input/output folderと再帰設定をpresetへ保存する。",
    #   "処理": ["現在設定を保存する", "名前・選択肢と結果logを更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"input_dir": self.input_dir.get(), "output_dir": self.output_dir.get(), "recursive": self.recursive.get()})
            self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択presetからinput/output folderと再帰設定を復元する。",
    #   "処理": ["保存値を各入力変数へ反映する", "読込結果をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.input_dir.set(values.get("input_dir", self.input_dir.get())); self.output_dir.set(values.get("output_dir", self.output_dir.get())); self.recursive.set(values.get("recursive", self.recursive.get()))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "tag分類処理をdaemon threadで開始する。",
    #   "処理": ["runをworker threadとして起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    # {
    #   "責務": "入力folderのtxtを走査しカテゴリ別の複製結果を生成する。",
    #   "処理": ["folderと対象file一覧を検証する", "TagCategorySplitterでfileごとに分類し相対pathと集計をlogへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
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
