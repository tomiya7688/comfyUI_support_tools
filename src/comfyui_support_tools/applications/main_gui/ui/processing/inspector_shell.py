"""Opt-in shell extension: one Action dispatcher for Inspector, toolbar and menu."""
import tkinter as tk
from tkinter import ttk

from comfyui_support_tools.applications.main_gui.ui.processing.shell_window import ShellWindow
from comfyui_support_tools.applications.main_gui.ui.processing.inspector_panel import InspectorPanel


class InspectorShellWindow(ShellWindow):
    def __init__(self, commander, on_open, media, inspector, jobs=None):
        super().__init__(commander, on_open, media, jobs)
        self.action_panel = InspectorPanel(self.inspector_text.master, inspector, self.append_log)
        self.action_panel.pack(fill="x", before=self.media_preview)
        self.action_panel.select(self.media_selection)
        button = ttk.Menubutton(self.toolbar, text="Actions")
        button.pack(side="right", padx=6)
        self.action_menu = tk.Menu(button, tearoff=False)
        self.action_menu.configure(postcommand=lambda: self.action_panel.fill_menu(self.action_menu))
        button.configure(menu=self.action_menu)
        self.context_menu = tk.Menu(self, tearoff=False)
        browser = self.workspace.media
        browser.grid_view.canvas.bind("<Button-3>", self._grid_context, add=True)
        browser.table.bind("<Button-3>", self._list_context, add=True)
        browser.grid_view.canvas.bind("<Shift-F10>", self._keyboard_context, add=True)
        browser.table.bind("<Shift-F10>", self._keyboard_context, add=True)

    def inspect_media(self, items):
        super().inspect_media(items)
        if hasattr(self, "action_panel"):
            self.action_panel.select(self.media_selection)
            if self.workspace.mode == "media":
                self.action_panel.pack(fill="x", before=self.media_preview)
            else:
                self.action_panel.pack_forget()
        if self.media_selection:
            item = self.media_selection[0]
            self.inspector_text.configure(text=f"{len(self.media_selection)}件選択\n{item.name}\n"
                                               f"{item.kind} / {item.size:,} B\n{item.path}")

    def inspect_tool(self, tool_id):
        super().inspect_tool(tool_id)
        if hasattr(self, "action_panel") and self.workspace.mode == "tools":
            self.action_panel.select(())
            self.action_panel.pack_forget()

    def _popup(self, x, y):
        self.action_panel.fill_menu(self.context_menu)
        try:
            self.context_menu.tk_popup(x, y)
        finally:
            self.context_menu.grab_release()
        return "break"

    def _grid_context(self, event):
        grid = self.workspace.media.grid_view
        column = int(grid.canvas.canvasx(event.x)) // grid.CELL_W
        row = int(grid.canvas.canvasy(event.y)) // grid.CELL_H
        index = row * grid.columns + column
        if 0 <= column < grid.columns and 0 <= index < len(grid.items):
            item = grid.items[index]
            if item.id not in grid.selected:
                grid._choose(index)
        else:
            self.workspace.media.select(())
        return self._popup(event.x_root, event.y_root)

    def _list_context(self, event):
        browser = self.workspace.media
        key = browser.table.identify_row(event.y)
        if not key:
            browser.select(())
        elif key not in browser.table.selection():
            browser.select((key,))
        return self._popup(event.x_root, event.y_root)

    def _keyboard_context(self, event):
        return self._popup(event.widget.winfo_rootx()+20, event.widget.winfo_rooty()+20)

    def destroy(self):
        if hasattr(self, "action_panel"):
            self.action_panel.close()
        super().destroy()
