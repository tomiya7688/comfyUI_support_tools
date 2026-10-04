from ..context import tk, ttk


# {
#   "責務": "タブの長い内容を縦scroll可能なcanvas内frameとして表示する。",
#   "フィールド": ["canvas: content viewport", "scrollbar: 縦scroll bar", "content: tab widget parent", "window_id: canvas内content item"]
# }
class ScrollableTabContainer(ttk.Frame):
    """縦長のタブ内容へ共通の縦スクロールを提供するコンテナ。"""

    # {
    #   "責務": "canvas、scrollbar、content frameとmousewheel bindingを作成する。",
    #   "処理": ["scroll commandを相互接続する", "canvas内へcontentを作りconfigure/enter/leave eventをbindする"],
    #   "引数": {"master": "親widget"}, "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._fit_content_width)
        self.canvas.bind("<Enter>", self._enable_mousewheel)
        self.canvas.bind("<Leave>", self._disable_mousewheel)

    # {
    #   "責務": "content size変更に合わせcanvas scrollregionを更新する。",
    #   "処理": ["canvas item boundsを取得しscrollregionへ反映する"],
    #   "引数": {"_event": "configure event。省略可"}, "戻り値": []
    # }
    def _update_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # {
    #   "責務": "canvas幅にcontent window itemの幅を合わせる。",
    #   "処理": ["configure event widthをcanvas itemへ設定する"],
    #   "引数": {"event": "canvas configure event"}, "戻り値": []
    # }
    def _fit_content_width(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    # {
    #   "責務": "pointerがcontainer上にある間mousewheel callbackを登録する。",
    #   "処理": ["application内MouseWheel eventを_on_mousewheelへbindする"],
    #   "引数": {"_event": "enter event。省略可"}, "戻り値": []
    # }
    def _enable_mousewheel(self, _event=None):
        self.bind_all("<MouseWheel>", self._on_mousewheel)

    # {
    #   "責務": "pointerがcontainerを離れた時mousewheel callbackを解除する。",
    #   "処理": ["application全体のMouseWheel bindingを解除する"],
    #   "引数": {"_event": "leave event。省略可"}, "戻り値": []
    # }
    def _disable_mousewheel(self, _event=None):
        self.unbind_all("<MouseWheel>")

    # {
    #   "責務": "mousewheel deltaを縦canvas scroll単位へ変換して適用する。",
    #   "処理": ["非zero deltaだけ反転方向のscroll単位に変換してyviewを動かす"],
    #   "引数": {"event": "mousewheel event"}, "戻り値": []
    # }
    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(-int(event.delta / 120), "units")
