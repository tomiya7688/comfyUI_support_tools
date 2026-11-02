"""Opt-in shell extension: one Action dispatcher for Inspector, toolbar and menu."""

import tkinter as tk
from tkinter import ttk

from comfyui_support_tools.applications.main_gui.ui.processing.shell_window import ShellWindow
from comfyui_support_tools.applications.main_gui.ui.processing.inspector_panel import InspectorPanel


# {
# 責務: [InspectorShellWindow: base shellにInspector Actions panel/menu/context menuを追加する]
# フィールド: [action_panel, action/context menus, inherited shell navigation/media state]
# }
class InspectorShellWindow(ShellWindow):
    # {
    #   責務: [__init__: base shell後にInspector panel、toolbar action menu、media context bindingsを追加する]
    #   処理: [shared controllersを受取りpanelを配置しgrid/list/keyboard context handlersをbindする]
    #   引数: [self: window, commander: navigation API, on_open: legacy callback, media: media commander, inspector: InspectorUiCommander, jobs: optional job queue]
    #   戻り値: [なし]
    #   副作用: [Tk panels/menusを作りcontext eventsをbindする]
    # }
    def __init__(self, commander, on_open, media, inspector, jobs=None):
        super().__init__(commander, on_open, media, jobs)
        self.action_panel = InspectorPanel(self.inspector_text.master, inspector, self.append_log)
        self.action_panel.pack(fill="x", before=self.media_preview)
        self.action_panel.select(self.media_selection)
        button = ttk.Menubutton(self.toolbar, text="Actions")
        button.pack(side="right", padx=6)
        self.action_menu = tk.Menu(button, tearoff=False)
        self.action_menu.configure(
            postcommand=lambda: self.action_panel.fill_menu(self.action_menu)
        )
        button.configure(menu=self.action_menu)
        self.context_menu = tk.Menu(self, tearoff=False)
        browser = self.workspace.media
        browser.grid_view.canvas.bind("<Button-3>", self._grid_context, add=True)
        browser.table.bind("<Button-3>", self._list_context, add=True)
        browser.grid_view.canvas.bind("<Shift-F10>", self._keyboard_context, add=True)
        browser.table.bind("<Shift-F10>", self._keyboard_context, add=True)

    # {
    #   責務: [inspect_media: base selection/previewを更新しmedia modeでInspector panelとfile detailsを同期する]
    #   処理: [action panelが利用可能な場合selectionを渡し、tools modeでは隠す]
    #   引数: [self: window, items: selected MediaItem sequence]
    #   戻り値: [None]
    #   副作用: [Inspector panel visibilityとsummary labelを更新する]
    # }
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
            self.inspector_text.configure(
                text=f"{len(self.media_selection)}件選択\n{item.name}\n"
                f"{item.kind} / {item.size:,} B\n{item.path}"
            )

    # {
    #   責務: [inspect_tool: legacy tool selectionをbase shellへ反映しmedia action panelを隠す]
    #   処理: [tools mode時にInspector selectionをclearする]
    #   引数: [self: window, tool_id: selected tool ID]
    #   戻り値: [None]
    #   副作用: [action panel state/visibilityを更新する]
    # }
    def inspect_tool(self, tool_id):
        super().inspect_tool(tool_id)
        if hasattr(self, "action_panel") and self.workspace.mode == "tools":
            self.action_panel.select(())
            self.action_panel.pack_forget()

    # {
    #   責務: [_popup: current availabilityでcontext menuを再作成し指定screen pointへ表示する]
    #   処理: [menu populate後tk_popupをtry/finallyで実行しgrabをreleaseする]
    #   引数: [self: window, x/y: screen coordinates]
    #   戻り値: ["break": Tk event propagationを止める]
    #   副作用: [Tk popup menu/grab stateを一時変更する]
    # }
    def _popup(self, x, y):
        self.action_panel.fill_menu(self.context_menu)
        try:
            self.context_menu.tk_popup(x, y)
        finally:
            self.context_menu.grab_release()
        return "break"

    # {
    #   責務: [_grid_context: pointer上grid itemを選択状態に合わせてcontext menuを開く]
    #   処理: [canvas coordinatesからindexを求め、outside hit時selection clear後popupする]
    #   引数: [self: window, event: Button-3 Tk event]
    #   戻り値: [popup result: "break"]
    #   副作用: [media selection/context menu stateを更新する]
    # }
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

    # {
    #   責務: [_list_context: pointer上Treeview rowを選択状態にしてcontext menuを開く]
    #   処理: [rowなしならclear、未選択rowならsingle selectしてpopupする]
    #   引数: [self: window, event: Button-3 Tk event]
    #   戻り値: [popup result: "break"]
    #   副作用: [media selection/context menu stateを更新する]
    # }
    def _list_context(self, event):
        browser = self.workspace.media
        key = browser.table.identify_row(event.y)
        if not key:
            browser.select(())
        elif key not in browser.table.selection():
            browser.select((key,))
        return self._popup(event.x_root, event.y_root)

    # {
    #   責務: [_keyboard_context: Shift-F10位置近傍にcontext menuを開く]
    #   処理: [event widget root originからoffset pointを作って_popupを呼ぶ]
    #   引数: [self: window, event: keyboard context Tk event]
    #   戻り値: [popup result: "break"]
    # }
    def _keyboard_context(self, event):
        return self._popup(event.widget.winfo_rootx() + 20, event.widget.winfo_rooty() + 20)

    # {
    #   責務: [destroy: Inspector action workerをcloseしてからbase shell resourcesをdestroyする]
    #   処理: [action_panel存在時closeしsuper.destroyを呼ぶ]
    #   引数: [self: window]
    #   戻り値: [None]
    #   副作用: [worker timer/resourceとTk windowを終了する]
    # }
    def destroy(self):
        if hasattr(self, "action_panel"):
            self.action_panel.close()
        super().destroy()
