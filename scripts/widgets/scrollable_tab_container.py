from ..context import tk, ttk


# {
#   責務: [ScrollableTabContainer: tall tab contents向けshared vertical scrolling containerを提供する]
#   処理: [compose canvas, scrollbar, content frame, and pointer bindings]
#   フィールド: [canvas, scrollbar, content, window_id]
# }
class ScrollableTabContainer(ttk.Frame):
    """縦長のタブ内容へ共通の縦スクロールを提供するコンテナ。"""

    # {
    #   責務: [__init__: canvas content and scroll event bindingsを初期化する]
    #   処理: [create and connect Tk widgets without file or model I/O]
    #   引数: [master]
    #   戻り値: [処理結果]
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
    #   責務: [_update_scroll_region: embedded contentに応じてcanvas scroll regionを更新する]
    #   処理: [set region to canvas item bounding box]
    #   引数: [_event]
    #   戻り値: [処理結果]
    # }
    def _update_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # {
    #   責務: [_fit_content_width: embedded content widthをcanvas viewportへ合わせる]
    #   処理: [resize canvas window item to current event width]
    #   引数: [event]
    #   戻り値: [処理結果]
    # }
    def _fit_content_width(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)

    # {
    #   責務: [_enable_mousewheel: container hover中のmouse wheel bindingを有効化する]
    #   処理: [bind global wheel events to this container handler]
    #   引数: [_event]
    #   戻り値: [処理結果]
    # }
    def _enable_mousewheel(self, _event=None):
        self.bind_all("<MouseWheel>", self._on_mousewheel)

    # {
    #   責務: [_disable_mousewheel: container leave時にglobal mouse wheel bindingを解除する]
    #   処理: [remove the global event binding]
    #   引数: [_event]
    #   戻り値: [処理結果]
    # }
    def _disable_mousewheel(self, _event=None):
        self.unbind_all("<MouseWheel>")

    # {
    #   責務: [_on_mousewheel: mouse wheel deltaをvertical canvas scrollへ変換する]
    #   処理: [scroll by delta-derived units when event has movement]
    #   引数: [event]
    #   戻り値: [処理結果]
    # }
    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(-int(event.delta / 120), "units")
