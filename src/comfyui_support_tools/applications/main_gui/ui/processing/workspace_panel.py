"""Fixed media/tools views; feature migration never adds more top-level tabs."""
from collections.abc import Callable
import tkinter as tk
from tkinter import ttk

from comfyui_support_tools.shared.contracts.tool_entry import ToolEntry
from comfyui_support_tools.applications.main_gui.ui.processing.media_browser_panel import MediaBrowserPanel


class WorkspacePanel(ttk.Frame):
    def __init__(self, master: tk.Misc, on_open: Callable[[str], None], on_select: Callable[[str], None],
                 media=None, on_media_select=None, on_media_preview=None):
        super().__init__(master, padding=16)
        self.title = ttk.Label(self, text="All / すべて", font=("TkDefaultFont", 18, "bold"))
        self.title.pack(anchor="w")
        self.mode = "tools"
        self._on_tool_select = on_select
        self._on_media_select = on_media_select
        switches = ttk.Frame(self)
        switches.pack(fill="x", pady=6)
        self.tools_frame = ttk.Frame(self)
        self.media = None
        if media is not None:
            self.media = MediaBrowserPanel(self, media, on_media_select, on_media_preview)
            ttk.Button(switches, text="メディア", command=self.show_media).pack(side="left")
        ttk.Button(switches, text="旧ツール一覧", command=self.show_tools).pack(side="left", padx=4)
        ttk.Label(self.tools_frame, text="移行中のツール — 旧UIで開きます", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(0, 8))
        table = ttk.Frame(self.tools_frame)
        table.pack(fill="both", expand=True)
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=("name", "category"), show="headings", selectmode="browse")
        self.tree.heading("name", text="機能")
        self.tree.heading("category", text="カテゴリ")
        self.tree.column("name", width=250, minwidth=130)
        self.tree.column("category", width=130, minwidth=90)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.empty = ttk.Label(self.tools_frame, text="")
        self.empty.pack(anchor="w", pady=6)
        self.open_button = ttk.Button(self.tools_frame, text="選択した機能を旧UIで開く", command=lambda: self._open(on_open), state="disabled")
        self.open_button.pack(anchor="w")
        self.tree.bind("<Double-1>", lambda _event: self._open(on_open))
        self.tree.bind("<Return>", lambda _event: self._open(on_open))
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._selected(on_select))
        if self.media is not None:
            self.mode = "media"
            self.media.pack(fill="both", expand=True)
        else:
            self.tools_frame.pack(fill="both", expand=True)

    def show_media(self):
        if self.media is not None:
            self.mode = "media"
            self.tools_frame.pack_forget()
            self.media.pack(fill="both", expand=True)
            self.media.restore_selection()

    def show_tools(self):
        self.mode = "tools"
        if self.media is not None:
            self.media.pack_forget()
            self._on_media_select(())
        self.tools_frame.pack(fill="both", expand=True)
        selection = self.tree.selection()
        self._on_tool_select(selection[0] if selection else "")

    def render(self, tools: tuple[ToolEntry, ...]) -> None:
        selection = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for tool in tools:
            self.tree.insert("", "end", iid=tool.id, values=(tool.label, tool.category))
        self.open_button.configure(state="disabled")
        if selection and self.tree.exists(selection[0]):
            self.tree.selection_set(selection[0])
        self.empty.configure(text=f"{len(tools)} 件" if tools else "該当する機能はありません。検索条件やRecentを確認してください。")

    def _selected(self, on_select: Callable[[str], None]) -> None:
        selection = self.tree.selection()
        self.open_button.configure(state="normal" if selection else "disabled")
        on_select(selection[0] if selection else "")

    def _open(self, on_open: Callable[[str], None]) -> None:
        selection = self.tree.selection()
        if selection:
            on_open(selection[0])
