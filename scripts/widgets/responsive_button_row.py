from __future__ import annotations

from tkinter import ttk


# {
#   "責務": "横幅に応じて子controlを複数行へ折り返すcontainer。",
#   "フィールド": ["controls: layout対象widgetの順序付きlist"]
# }
class ResponsiveButtonRow(ttk.Frame):
    """Wrap child controls onto additional rows when the available width is small."""

    # {
    #   "責務": "responsive rowを初期化しconfigure eventをlayout callbackへ接続する。",
    #   "処理": ["ttk.Frameを初期化する", "control listを作りresize bindingを設定する"],
    #   "引数": {"master": "親widget", "kwargs": "Frame option"}, "戻り値": []
    # }
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.controls = []
        self.bind("<Configure>", self._layout)

    # {
    #   "責務": "controlをrowへ登録して現widthに従い配置し返す。",
    #   "処理": ["controlを順序末尾へ追加する", "layoutを再計算する"],
    #   "引数": {"control": "配置するTk widget"}, "戻り値": "追加したcontrol"
    # }
    def add(self, control):
        self.controls.append(control)
        self._layout()
        return control

    # {
    #   "責務": "現在のcontainer widthに合わせてcontrolをgrid行へ折り返す。",
    #   "処理": ["widget requested widthを累積する", "幅超過前に次行へ進みcontrolを配置する"],
    #   "引数": {"_event": "configure event。省略可"}, "戻り値": []
    # }
    def _layout(self, _event=None):
        if not self.controls:
            return
        width = max(1, self.winfo_width())
        row = column = used = 0
        for control in self.controls:
            requested = max(80, control.winfo_reqwidth()) + 8
            if column and used + requested > width:
                row += 1; column = 0; used = 0
            control.grid(row=row, column=column, padx=4, pady=2, sticky="w")
            used += requested; column += 1
        for index in range(column):
            self.columnconfigure(index, weight=0)
