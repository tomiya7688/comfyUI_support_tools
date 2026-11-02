from __future__ import annotations
import threading
from pathlib import Path
from ..context import *
from ..backend.docstring_auditor import DocstringAuditor
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore


# {
#   責務: [DocstringAuditTab: Python source docstring audit and Markdown report tabを提供する]
#   処理: [create target/output controls, recursion option, and audit actions]
#   フィールド: [target, output, recursive, preset state, logbox]
# }
class DocstringAuditTab(ttk.Frame):
    # {
    #   責務: [__init__: audit target, output, recursion, and preset stateを初期化する]
    #   処理: [create Tk variables and build user controls]
    #   引数: [master]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.target = tk.StringVar()
        self.output = tk.StringVar(value=str(USER_DATA_DIR / "output" / "docstring_audit.md"))
        self.recursive = tk.BooleanVar(value=True)
        self.preset_name = tk.StringVar()
        self.preset_store = PresetStore("docstring_audit")
        self._build()

    # {
    #   責務: [_build: target chooser, report path, recursive option, and run buttonを構築する]
    #   処理: [compose UI widgets and log output]
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
            self, "レポートMarkdown", self.output, mode="save", filetypes=[("Markdown", "*.md")]
        ).pack(fill="x", pady=3)
        ttk.Checkbutton(self, text="サブフォルダも検査", variable=self.recursive).pack(anchor="w")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="検査開始", command=self.start).pack(side="left")
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    # {
    #   責務: [_choose: file or directory chooserからaudit targetを選択する]
    #   処理: [show chooser according to folder flag and update target on selection]
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
    #   責務: [start: audit workerをbackground threadで開始する]
    #   処理: [spawn run without blocking the GUI]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    # {
    #   責務: [run: selected Python targetをauditしMarkdown reportへ保存する]
    #   処理: [validate path, run DocstringAuditor, write report, and log result or failure]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def run(self):
        try:
            target, output = Path(self.target.get().strip()), Path(self.output.get().strip())
            if not (target.is_file() or target.is_dir()):
                raise ValueError(f"対象がありません: {target}")
            auditor = DocstringAuditor()
            results = auditor.audit(target, self.recursive.get())
            count = auditor.write_report(results, output)
            self.logbox.log(f"検査完了: {len(results)}ファイル / 不足 {count}件 / {output}")
        except Exception as error:
            self.logbox.log(f"検査エラー: {error}")
