from __future__ import annotations

from tkinter import ttk


class DarkTheme:
    """Apply the shared black visual theme to the Tk application."""

    BACKGROUND = "#0b0b0b"
    PANEL = "#171717"
    INPUT = "#202020"
    BORDER = "#454545"
    TEXT = "#eeeeee"
    MUTED = "#b8b8b8"
    ACCENT = "#3977c6"
    ACTIVE = "#28558d"

    def apply(self, root) -> None:
        root.configure(bg=self.BACKGROUND)
        root.option_add("*Text.Background", self.INPUT)
        root.option_add("*Text.Foreground", self.TEXT)
        root.option_add("*Text.InsertBackground", self.TEXT)
        root.option_add("*Text.SelectBackground", self.ACCENT)
        root.option_add("*Text.SelectForeground", self.TEXT)
        root.option_add("*Canvas.Background", self.BACKGROUND)
        root.option_add("*Canvas.HighlightBackground", self.BACKGROUND)
        root.option_add("*Listbox.Background", self.INPUT)
        root.option_add("*Listbox.Foreground", self.TEXT)
        root.option_add("*Listbox.SelectBackground", self.ACCENT)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=self.BACKGROUND, foreground=self.TEXT, fieldbackground=self.INPUT, bordercolor=self.BORDER)
        style.configure("TFrame", background=self.BACKGROUND)
        style.configure("TLabel", background=self.BACKGROUND, foreground=self.TEXT)
        style.configure("TButton", background="#292929", foreground=self.TEXT, bordercolor=self.BORDER, padding=(8, 4))
        style.map("TButton", background=[("active", self.ACTIVE), ("pressed", self.ACCENT)], foreground=[("disabled", "#777777")])
        style.configure("TCheckbutton", background=self.BACKGROUND, foreground=self.TEXT)
        style.map("TCheckbutton", background=[("active", self.BACKGROUND)], foreground=[("active", self.TEXT)])
        style.configure("TEntry", fieldbackground=self.INPUT, foreground=self.TEXT, insertcolor=self.TEXT, bordercolor=self.BORDER)
        style.configure("TCombobox", fieldbackground=self.INPUT, foreground=self.TEXT, background="#292929", arrowcolor=self.TEXT, bordercolor=self.BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", self.INPUT)], selectbackground=[("readonly", self.INPUT)], selectforeground=[("readonly", self.TEXT)])
        style.configure("TLabelframe", background=self.BACKGROUND, foreground=self.TEXT, bordercolor=self.BORDER)
        style.configure("TLabelframe.Label", background=self.BACKGROUND, foreground=self.TEXT)
        style.configure("Treeview", background=self.INPUT, fieldbackground=self.INPUT, foreground=self.TEXT, bordercolor=self.BORDER, rowheight=24)
        style.configure("Treeview.Heading", background="#292929", foreground=self.TEXT, bordercolor=self.BORDER)
        style.map("Treeview", background=[("selected", self.ACCENT)], foreground=[("selected", self.TEXT)])
        style.configure("TScrollbar", background="#292929", troughcolor=self.BACKGROUND, bordercolor=self.BORDER, arrowcolor=self.TEXT)
