"""Library navigation for local media and legacy-tool migration."""

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk

LABELS = {
    "all": "All / すべて",
    "images": "Images / 画像",
    "videos": "Videos / 動画",
    "dataset": "Dataset",
    "generated": "Generated / 生成物",
    "favorites": "Favorites / お気に入り",
    "recent": "Recent / 最近使用",
}


# {
# 責務: [LibraryPanel: fixed media/navigation section treeを表示してselectionをcallbackする]
# フィールド: [tree: section keyとlabelを持つTreeview]
# }
class LibraryPanel(ttk.Frame):
    # {
    #   責務: [__init__: supported Library section rowsとselection bindingを構築する]
    #   処理: [LABELSからtree rowsを作りallをdefault selectする]
    #   引数: [self: panel, master: parent widget, on_select: selected section callback]
    #   戻り値: [なし]
    #   副作用: [Tk Treeview/labelsを生成しselection eventをbindする]
    # }
    def __init__(self, master: tk.Misc, on_select: Callable[[str], None]):
        super().__init__(master, padding=12, width=210)
        ttk.Label(self, text="LIBRARY", font=("TkDefaultFont", 11, "bold")).pack(
            anchor="w", pady=(0, 12)
        )
        self.tree = ttk.Treeview(self, show="tree", selectmode="browse", height=9)
        self.tree.column("#0", width=175, minwidth=100)
        self.tree.pack(fill="both", expand=True)
        for key, label in LABELS.items():
            self.tree.insert("", "end", iid=key, text=label)
        self.tree.selection_set("all")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._selected(on_select))
        ttk.Label(
            self,
            text="Media: 選択フォルダ内\n★ / Recent: 今回のセッション\n旧ツール一覧も切替可能",
            wraplength=180,
        ).pack(anchor="w", pady=12)

    # {
    #   責務: [_selected: current Treeview selectionがあればsection keyをcallbackへ通知する]
    #   処理: [selection tupleの先頭keyだけをon_selectへ渡す]
    #   引数: [self: panel, on_select: selected section callback]
    #   戻り値: [None]
    #   副作用: [on_selectを呼ぶ]
    # }
    def _selected(self, on_select: Callable[[str], None]) -> None:
        selection = self.tree.selection()
        if selection:
            on_select(selection[0])
