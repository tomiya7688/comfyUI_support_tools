import tkinter as tk
from tkinter import ttk


# {
#   責務: [TabNavigation: two-row tab buttons向けhorizontal scrolling navigationを提供する]
#   処理: [compose canvas, scrollbar, child rows, and scroll bindings]
#   フィールド: [canvas, scrollbar, content, first_row, second_row, window]
# }
class TabNavigation(ttk.Frame):
    """横幅を超えるタブボタンを横スクロールで扱うナビゲーション。"""

    # {
    #   責務: [__init__: navigation canvas, scrollbar, and two button rowsを初期化する]
    #   処理: [connect horizontal scroll state and configure content event handling]
    #   引数: [master]
    #   戻り値: [処理結果]
    # }
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

    # {
    #   責務: [_update_scroll_region: tab button contentに応じてhorizontal canvas regionを更新する]
    #   処理: [set scroll region to child bounding box]
    #   引数: [_event]
    #   戻り値: [処理結果]
    # }
    def _update_scroll_region(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # {
    #   責務: [_scroll_horizontal: shift-wheel deltaをhorizontal canvas scrollへ変換する]
    #   処理: [scroll one unit according to event direction]
    #   引数: [event]
    #   戻り値: [処理結果]
    # }
    def _scroll_horizontal(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
