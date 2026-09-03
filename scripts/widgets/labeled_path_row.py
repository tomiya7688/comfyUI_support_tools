from ..context import *

class LabeledPathRow(ttk.Frame):
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

    def browse_file(self) -> None:
        initial = self.var.get().strip()
        path = filedialog.askopenfilename(initialdir=os.path.dirname(initial) if initial else os.getcwd(), filetypes=self.filetypes)
        if path:
            self.var.set(path)

    def browse_directory(self) -> None:
        initial = self.var.get().strip()
        path = filedialog.askdirectory(initialdir=initial if os.path.isdir(initial) else (os.path.dirname(initial) if initial else os.getcwd()))
        if path:
            self.var.set(path)
