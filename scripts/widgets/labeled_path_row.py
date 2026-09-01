from ..context import *

class LabeledPathRow(ttk.Frame):
    def __init__(self, master, label: str, var: tk.StringVar, mode: str = "file", filetypes=None):
        super().__init__(master)
        self.var = var
        self.mode = mode
        self.filetypes = filetypes or [("All files", "*.*")]
        ttk.Label(self, text=label, width=22).pack(side="left", padx=(0, 6))
        ttk.Entry(self, textvariable=var).pack(side="left", fill="x", expand=True)
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
