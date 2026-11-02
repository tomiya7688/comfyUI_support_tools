from ..context import *


# {
#   責務: [LabeledPathRow: label, editable path variable, and browse controlsをまとめたrowを提供する]
#   処理: [compose Tk widgets and delegate filesystem selection to dialogs]
#   フィールド: [var, mode, filetypes, child controls]
# }
class LabeledPathRow(ttk.Frame):
    # {
    #   責務: [__init__: path row controls and selection modeを初期化する]
    #   処理: [store path variable and create label, entry, and mode-appropriate buttons]
    #   引数: [master, label, var, mode, filetypes]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master, label: str, var: tk.StringVar, mode: str = "file", filetypes=None):
        super().__init__(master)
        self.var = var
        self.mode = mode
        self.filetypes = filetypes or [("All files", "*.*")]
        ttk.Label(self, text=label, width=22).pack(side="left", padx=(0, 6))
        ttk.Entry(self, textvariable=var).pack(side="left", fill="x", expand=True)
        if self.mode == "file_or_dir":
            ttk.Button(self, text="ファイル", command=self.browse_file).pack(
                side="left", padx=(6, 0)
            )
            ttk.Button(self, text="フォルダ", command=self.browse_directory).pack(
                side="left", padx=(4, 0)
            )
        else:
            ttk.Button(self, text="参照", command=self.browse).pack(side="left", padx=(6, 0))

    # {
    #   責務: [browse: configured modeに応じたopen/save file or directory dialogを表示する]
    #   処理: [derive initial location, open dialog, and update variable only when selected]
    #   引数: [なし]
    #   戻り値: [None]
    # }
    def browse(self) -> None:
        initial = self.var.get().strip()
        initialdir = os.path.dirname(initial) if initial else os.getcwd()
        if self.mode == "dir":
            path = filedialog.askdirectory(initialdir=initialdir or os.getcwd())
        elif self.mode == "save":
            path = filedialog.asksaveasfilename(
                initialdir=initialdir or os.getcwd(),
                defaultextension=".txt",
                filetypes=self.filetypes,
            )
        else:
            path = filedialog.askopenfilename(
                initialdir=initialdir or os.getcwd(),
                filetypes=self.filetypes,
            )
        if path:
            self.var.set(path)

    # {
    #   責務: [browse_file: file-open dialogでpathを選択する]
    #   処理: [derive initial directory, show configured filetypes, and update variable on selection]
    #   引数: [なし]
    #   戻り値: [None]
    # }
    def browse_file(self) -> None:
        initial = self.var.get().strip()
        path = filedialog.askopenfilename(
            initialdir=os.path.dirname(initial) if initial else os.getcwd(),
            filetypes=self.filetypes,
        )
        if path:
            self.var.set(path)

    # {
    #   責務: [browse_directory: directory selection dialogでpathを選択する]
    #   処理: [derive existing initial directory, show dialog, and update variable on selection]
    #   引数: [なし]
    #   戻り値: [None]
    # }
    def browse_directory(self) -> None:
        initial = self.var.get().strip()
        path = filedialog.askdirectory(
            initialdir=initial
            if os.path.isdir(initial)
            else (os.path.dirname(initial) if initial else os.getcwd())
        )
        if path:
            self.var.set(path)
