from ..context import *

# {
#   "責務": "path変数を表示し、指定modeのfile/folder dialogから値を設定する共通row。",
#   "フィールド": ["var: path値を保持するTk variable", "mode: file/dir/save/file_or_dir選択種別", "filetypes: file dialog filter"]
# }
class LabeledPathRow(ttk.Frame):
    # {
    #   "責務": "label、path entry、参照buttonを組み立てる。",
    #   "処理": ["path variableとdialog条件を保持する", "modeに応じたchooser buttonを配置する"],
    #   "引数": {"master": "親widget", "label": "row label", "var": "path StringVar", "mode": "dialog種別", "filetypes": "file filter。省略可"}, "戻り値": []
    # }
    def __init__(self, master, label: str, var: tk.StringVar, mode: str = "file", filetypes=None):
        super().__init__(master)
        self.var = var
        self.mode = mode
        self.filetypes = filetypes or [("All files", "*.*")]
        ttk.Label(self, text=label, width=22).pack(side="left", padx=(0, 6))
        ttk.Entry(self, textvariable=var).pack(side="left", fill="x", expand=True)
        if self.mode == "file_or_dir":
            ttk.Button(self, text="ファイル", command=self.browse_file).pack(side="left", padx=(6, 0))
            ttk.Button(self, text="フォルダ", command=self.browse_directory).pack(side="left", padx=(4, 0))
        else:
            ttk.Button(self, text="参照", command=self.browse).pack(side="left", padx=(6, 0))

    # {
    #   "責務": "modeに応じたfile/save/folder dialogを開き選択結果をpath変数へ設定する。",
    #   "処理": ["現在値からinitial directoryを決める", "適切なdialogを開き選択pathがあれば保存する"],
    #   "引数": [], "戻り値": []
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
    #   "責務": "file chooserを開いて選択file pathを変数へ保存する。",
    #   "処理": ["既存pathに基づき初期directoryを設定する", "選択された値をvarへ反映する"],
    #   "引数": [], "戻り値": []
    # }
    def browse_file(self) -> None:
        initial = self.var.get().strip()
        path = filedialog.askopenfilename(initialdir=os.path.dirname(initial) if initial else os.getcwd(), filetypes=self.filetypes)
        if path:
            self.var.set(path)

    # {
    #   "責務": "directory chooserを開いて選択folder pathを変数へ保存する。",
    #   "処理": ["既存directoryまたはそのparentを初期値に選ぶ", "選択された値をvarへ反映する"],
    #   "引数": [], "戻り値": []
    # }
    def browse_directory(self) -> None:
        initial = self.var.get().strip()
        path = filedialog.askdirectory(initialdir=initial if os.path.isdir(initial) else (os.path.dirname(initial) if initial else os.getcwd()))
        if path:
            self.var.set(path)
