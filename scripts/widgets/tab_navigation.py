import tkinter as tk
from tkinter import ttk


class TabNavigation(ttk.Frame):
    """横幅を超えるタブボタンを横スクロールで扱うナビゲーション。"""

    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, height=70, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=self.scrollbar.set)
        self.canvas.pack(fill="x", expand=True)
        self.scrollbar.pack(fill="x")
        self.content = ttk.Frame(self.canvas)
        self.first_row = ttk.Frame(self.content)
        self.second_row = ttk.Frame(self.content)
        self.first_row.pack(anchor="w")
        self.second_row.pack(anchor="w")
        self.window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Shift-MouseWheel>", self._scroll_horizontal)

    def _update_scroll_region(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _scroll_horizontal(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
