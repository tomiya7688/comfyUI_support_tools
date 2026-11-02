from __future__ import annotations

from tkinter import ttk


# {
#   責務: [ResponsiveButtonRow: available widthに合わせてchild controlsを折り返すttk rowを提供する]
#   処理: [track child widgets and relayout them on Configure events]
#   フィールド: [controls]
# }
class ResponsiveButtonRow(ttk.Frame):
    """Wrap child controls onto additional rows when the available width is small."""

    # {
    #   責務: [__init__: responsive row state and configure handlerを初期化する]
    #   処理: [create frame, initialize controls, and bind responsive layout]
    #   引数: [master, **kwargs]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.controls = []
        self.bind("<Configure>", self._layout)

    # {
    #   責務: [add: controlをrowへ登録してlayout後に返す]
    #   処理: [append widget, recompute grid positions, and return widget]
    #   引数: [control]
    #   戻り値: [処理結果]
    # }
    def add(self, control):
        self.controls.append(control)
        self._layout()
        return control

    # {
    #   責務: [_layout: child controlsをrequested widthに応じた複数grid rowへ配置する]
    #   処理: [compute row wrapping from widget widths and available frame width]
    #   引数: [_event]
    #   戻り値: [処理結果]
    # }
    def _layout(self, _event=None):
        if not self.controls:
            return
        width = max(1, self.winfo_width())
        row = column = used = 0
        for control in self.controls:
            requested = max(80, control.winfo_reqwidth()) + 8
            if column and used + requested > width:
                row += 1
                column = 0
                used = 0
            control.grid(row=row, column=column, padx=4, pady=2, sticky="w")
            used += requested
            column += 1
        for index in range(column):
            self.columnconfigure(index, weight=0)
