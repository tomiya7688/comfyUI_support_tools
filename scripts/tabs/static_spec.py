from __future__ import annotations
import threading
from pathlib import Path
from ..context import *
from ..backend.static_spec_generator import StaticSpecGenerator
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore


# {
#   責務: [StaticSpecTab: Python source static specification report UI and presetsを管理する]
#   処理: [create source/output controls, recursion option, and generation action]
#   フィールド: [target, output, recursive, preset_name, preset_store, logbox]
# }
class StaticSpecTab(ttk.Frame):
    # {
    #   責務: [__init__: audit source, output, and preset stateを初期化する]
    #   処理: [initialize Tk variables and build controls]
    #   引数: [master]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.target = tk.StringVar()
        self.output = tk.StringVar(value=str(USER_DATA_DIR / "output" / "static_spec.md"))
        self.recursive = tk.BooleanVar(value=True)
        self.preset_name = tk.StringVar()
        self.preset_store = PresetStore("static_spec")
        self._build()

    # {
    #   責務: [_build: source chooser, Markdown output, recursion option, and preset controlsを構築する]
    #   処理: [compose GUI and log widgets]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _build(self):
        row = ttk.Frame(self)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="Pythonファイル / フォルダ", width=22).pack(side="left")
        ttk.Entry(row, textvariable=self.target).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="ファイル", command=lambda: self._choose(False)).pack(
            side="left", padx=3
        )
        ttk.Button(row, text="フォルダ", command=lambda: self._choose(True)).pack(side="left")
        LabeledPathRow(
            self,
            "出力Markdown",
            self.output,
            mode="save",
            filetypes=[("Markdown", "*.md"), ("All", "*.*")],
        ).pack(fill="x", pady=3)
        ttk.Checkbutton(self, text="サブフォルダも解析", variable=self.recursive).pack(anchor="w")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="仕様書を生成", command=self.start).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self._refresh()

    # {
    #   責務: [_choose: file or folder dialogからsource pathを選択する]
    #   処理: [show dialog based on folder flag and update target on selection]
    #   引数: [folder]
    #   戻り値: [処理結果]
    # }
    def _choose(self, folder):
        path = (
            filedialog.askdirectory()
            if folder
            else filedialog.askopenfilename(filetypes=[("Python", "*.py")])
        )
        if path:
            self.target.set(path)

    # {
    #   責務: [_refresh: preset dropdownをavailable namesで更新する]
    #   処理: [query PresetStore and configure combobox]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _refresh(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   責務: [save_preset: source, output, and recursion settingsをpresetへ保存する]
    #   処理: [write current values and refresh preset selector]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def save_preset(self):
        path = self.preset_store.save(
            self.preset_name.get(),
            {
                "target": self.target.get(),
                "output": self.output.get(),
                "recursive": self.recursive.get(),
            },
        )
        self.preset_name.set(path.stem)
        self._refresh()
        self.logbox.log(f"プリセットを保存しました: {path}")

    # {
    #   責務: [load_preset: presetからsource, output, and recursion settingsを復元する]
    #   処理: [read values into Tk controls]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def load_preset(self):
        values = self.preset_store.load(self.preset_name.get())
        self.target.set(values.get("target", self.target.get()))
        self.output.set(values.get("output", self.output.get()))
        self.recursive.set(values.get("recursive", self.recursive.get()))
        self.logbox.log("プリセットを読み込みました")

    # {
    #   責務: [start: static spec generationをdaemon threadで開始する]
    #   処理: [spawn run callback without blocking GUI]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    # {
    #   責務: [run: selected sourceを解析しstatic specification Markdownを生成する]
    #   処理: [validate path, call StaticSpecGenerator with recursion option, and log result or error]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def run(self):
        try:
            target, output = Path(self.target.get().strip()), Path(self.output.get().strip())
            if not (target.is_file() or target.is_dir()):
                raise ValueError(f"対象がありません: {target}")
            count = StaticSpecGenerator().generate_files(target, output, self.recursive.get())
            self.logbox.log(f"生成完了: {count}ファイル / {output}")
        except Exception as error:
            self.logbox.log(f"生成エラー: {error}")
