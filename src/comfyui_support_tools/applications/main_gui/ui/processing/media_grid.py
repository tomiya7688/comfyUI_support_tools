"""Page-bounded thumbnail grid, with mouse/keyboard multi-selection."""

import base64
import math
import tkinter as tk
from tkinter import ttk


# {
# 責務: [MediaGrid: current page thumbnailsをcanvasへ描きmouse/keyboard multi-selectionを処理する]
# フィールド: [items, selected IDs, image refs, anchor index, columns, canvas, on_select callback]
# }
class MediaGrid(ttk.Frame):
    CELL_W, CELL_H = 154, 166

    # {
    #   責務: [__init__: scrollable canvasを作りselection/navigation/wheel eventをbindする]
    #   処理: [cell stateを初期化しmouse, Ctrl-A, arrow/Home/End, platform wheel handlersを登録する]
    #   引数: [self: grid, master: parent, on_select: selected ID tuple callback]
    #   戻り値: [なし]
    #   副作用: [Tk canvas/scrollbar/bindingsを生成する]
    # }
    def __init__(self, master, on_select):
        super().__init__(master)
        self.on_select = on_select
        self.items = ()
        self.selected = set()
        self.images = {}
        self.anchor = 0
        self.columns = 1
        self.canvas = tk.Canvas(self, highlightthickness=0, takefocus=True)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Control-a>", self._all)
        for key in ("Left", "Right", "Up", "Down", "Home", "End"):
            self.canvas.bind("<" + key + ">", self._key)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(1, "units"))

    # {
    #   責務: [render: 新しいpage items/selectionでcell stateをresetしてcanvasを描き直す]
    #   処理: [thumbnail refsをclearしanchor/y offsetを先頭へ戻す]
    #   引数: [self: grid, items: visible MediaItem page, selected: selected ID iterable]
    #   戻り値: [なし]
    #   副作用: [canvas contentとscroll positionを更新する]
    # }
    def render(self, items, selected):
        self.items = items
        self.selected = set(selected)
        self.images = {}
        self.anchor = 0
        self.canvas.yview_moveto(0)
        self.redraw()

    # {
    #   責務: [set_preview: PNG previewをPhotoImageへdecodeしitem IDに紐付ける]
    #   処理: [pngありはimage reference、empty/errorはNoneとして保持する]
    #   引数: [self: grid, preview: MediaPreview contract]
    #   戻り値: [なし]
    #   副作用: [Tk PhotoImageを作成しimage cacheを更新する]
    # }
    def set_preview(self, preview):
        if preview.png:
            self.images[preview.item_id] = tk.PhotoImage(
                master=self.canvas, data=base64.b64encode(preview.png)
            )
        else:
            self.images[preview.item_id] = None

    # {
    #   責務: [redraw: viewport幅からcolumn数を決めcurrent itemsをtheme対応cellとして描く]
    #   処理: [scrollregion/selection colors/placeholders/name labelsとthumbnail positionsを再構築する]
    #   引数: [self: grid]
    #   戻り値: [なし]
    #   副作用: [Canvas contents/style-derived colorsを更新する]
    # }
    def redraw(self):
        canvas = self.canvas
        canvas.delete("all")
        self.columns = max(1, canvas.winfo_width() // self.CELL_W)
        rows = math.ceil(len(self.items) / self.columns)
        canvas.configure(scrollregion=(0, 0, self.columns * self.CELL_W, rows * self.CELL_H))
        style = ttk.Style(self)
        background = style.lookup("TFrame", "background") or "#f0f0f0"
        foreground = style.lookup("TLabel", "foreground") or "#202020"
        selection_bg = style.lookup("Treeview", "background", ("selected",)) or "#2d60a5"
        selection_fg = style.lookup("Treeview", "foreground", ("selected",)) or "#ffffff"
        canvas.configure(background=background)
        for index, item in enumerate(self.items):
            x = (index % self.columns) * self.CELL_W
            y = (index // self.columns) * self.CELL_H
            selected = item.id in self.selected
            fg = selection_fg if selected else foreground
            canvas.create_rectangle(
                x + 3,
                y + 3,
                x + self.CELL_W - 3,
                y + self.CELL_H - 3,
                fill=selection_bg if selected else background,
                outline=foreground,
            )
            photo = self.images.get(item.id)
            if photo:
                canvas.create_image(x + 77, y + 66, image=photo)
            else:
                caption = "IMAGE" if item.kind == "image" else "VIDEO"
                if item.id in self.images:
                    caption += " / 読込不可"
                canvas.create_text(x + 77, y + 65, text=caption, fill=fg)
            canvas.create_text(x + 77, y + 141, text=item.name[:36], width=144, fill=fg)

    # {
    #   責務: [_choose: indexに応じsingle/Ctrl-toggle/Shift-range selectionを更新する]
    #   処理: [visible page bounds確認、anchor処理、draw後ID tupleをcallbackへ通知する]
    #   引数: [self: grid, index: clicked/focused row index, control: additive toggle flag, shift: range flag]
    #   戻り値: [None]
    #   副作用: [selection/canvasを更新しon_selectを呼ぶ]
    # }
    def _choose(self, index, control=False, shift=False):
        if not 0 <= index < len(self.items):
            return
        if shift:
            start, end = sorted((self.anchor, index))
            keys = {item.id for item in self.items[start : end + 1]}
            self.selected = self.selected | keys if control else keys
        elif control:
            key = self.items[index].id
            self.selected.symmetric_difference_update({key})
            self.anchor = index
        else:
            self.selected = {self.items[index].id}
            self.anchor = index
        self.redraw()
        self.on_select(tuple(item.id for item in self.items if item.id in self.selected))

    # {
    #   責務: [_click: canvas pixel coordinateをgrid cell indexへ変換してmouse selectionを処理する]
    #   処理: [focusを設定しcanvas scroll offset/column countからindexを算出する]
    #   引数: [self: grid, event: Button-1 Tk event]
    #   戻り値: [None]
    #   副作用: [_choose経由でselectionを更新する]
    # }
    def _click(self, event):
        self.canvas.focus_set()
        row = int(self.canvas.canvasy(event.y)) // self.CELL_H
        column = int(self.canvas.canvasx(event.x)) // self.CELL_W
        if column < self.columns:
            self._choose(row * self.columns + column, bool(event.state & 4), bool(event.state & 1))

    # {
    #   責務: [_all: current page itemsを全選択してkeyboard eventを消費する]
    #   処理: [IDsを選択しredraw後callbackを実行する]
    #   引数: [self: grid, _event: optional Ctrl-A event]
    #   戻り値: ["break": Tk default actionを止める]
    #   副作用: [selection/canvasを更新する]
    # }
    def _all(self, _event=None):
        self.selected = {item.id for item in self.items}
        self.redraw()
        self.on_select(tuple(item.id for item in self.items))
        return "break"

    # {
    #   責務: [_key: arrow/Home/End keyboard movementを選択しvisible rowへscrollする]
    #   処理: [anchorとmodifierを使いindexをclampし_shift range、focus、yviewを更新する]
    #   引数: [self: grid, event: Tk key event]
    #   戻り値: ["break": Tk default handlingを止める]
    #   副作用: [selection/canvas scrollを更新する]
    # }
    def _key(self, event):
        index = self.anchor
        if event.keysym == "Home":
            index = 0
        elif event.keysym == "End":
            index = len(self.items) - 1
        else:
            index += {"Left": -1, "Right": 1, "Up": -self.columns, "Down": self.columns}[
                event.keysym
            ]
        self._choose(max(0, min(len(self.items) - 1, index)), shift=bool(event.state & 1))
        if not event.state & 1:
            self.anchor = max(0, min(len(self.items) - 1, index))
        rows = max(1, math.ceil(len(self.items) / self.columns))
        self.canvas.yview_moveto((max(0, index) // self.columns) / rows)
        return "break"

    # {
    #   責務: [_wheel: wheel deltaに従いcanvasをvertical方向へscrollする]
    #   処理: [delta符号を上/下unit stepへ変換する]
    #   引数: [self: grid, event: platform MouseWheel event]
    #   戻り値: ["break": parent scroll handlerへ伝播させない]
    #   副作用: [canvas yviewを動かす]
    # }
    def _wheel(self, event):
        self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"
