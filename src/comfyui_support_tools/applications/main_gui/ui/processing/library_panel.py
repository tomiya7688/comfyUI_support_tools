"""Library navigation for local media and legacy-tool migration."""
from collections.abc import Callable
import tkinter as tk
from tkinter import ttk

LABELS = {
    "all": "All / すべて", "images": "Images / 画像", "videos": "Videos / 動画",
    "dataset": "Dataset", "generated": "Generated / 生成物",
    "favorites": "Favorites / お気に入り", "recent": "Recent / 最近使用",
}


class LibraryPanel(ttk.Frame):
    def __init__(self, master: tk.Misc, on_select: Callable[[str], None]):
        super().__init__(master, padding=12, width=210)
        ttk.Label(self, text="LIBRARY", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(0, 12))
        self.tree = ttk.Treeview(self, show="tree", selectmode="browse", height=9)
        self.tree.column("#0", width=175, minwidth=100)
        self.tree.pack(fill="both", expand=True)
        for key, label in LABELS.items():
            self.tree.insert("", "end", iid=key, text=label)
        self.tree.selection_set("all")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._selected(on_select))
        ttk.Label(self, text="Media: 選択フォルダ内\n★ / Recent: 今回のセッション\n旧ツール一覧も切替可能", wraplength=180).pack(anchor="w", pady=12)

    def _selected(self, on_select: Callable[[str], None]) -> None:
        selection = self.tree.selection()
        if selection:
            on_select(selection[0])
