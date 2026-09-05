from __future__ import annotations

from tkinter import ttk


class ResponsiveButtonRow(ttk.Frame):
    """Wrap child controls onto additional rows when the available width is small."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.controls = []
        self.bind("<Configure>", self._layout)

    def add(self, control):
        self.controls.append(control)
        self._layout()
        return control

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
