import tkinter as tk
from tkinter import ttk


# {
#   "責務": "二段配置のtab navigationを横scroll可能なcanvasに収める。",
#   "フィールド": ["canvas: navigation viewport", "scrollbar: 横scroll bar", "content: button rows container", "first_row/second_row: tab button rows", "window: canvas window item"]
# }
class TabNavigation(ttk.Frame):
    """横幅を超えるタブボタンを横スクロールで扱うナビゲーション。"""

    # {
    #   "責務": "horizontal canvasとscrollbar、および二段button rowを構築する。",
    #   "処理": ["canvas scroll commandを接続する", "二段rowをcanvas windowへ配置し幅変更・shift-wheel eventをbindする"],
    #   "引数": {"master": "親widget"}, "戻り値": []
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
    #   "責務": "navigation content変更時にcanvas horizontal scrollregionを更新する。",
    #   "処理": ["content boundsをcanvas scrollregionへ設定する"],
    #   "引数": {"_event": "configure event"}, "戻り値": []
    # }
    def _update_scroll_region(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # {
    #   "責務": "Shift+mousewheel deltaに応じてnavigationを横scrollする。",
    #   "処理": ["delta方向を1単位のcanvas xview scrollへ変換する"],
    #   "引数": {"event": "shift mousewheel event"}, "戻り値": []
    # }
    def _scroll_horizontal(self, event):
        self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
