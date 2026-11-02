"""Read-only media browser UI. Workers communicate through bounded DTO queues."""

from datetime import datetime
import time
import tkinter as tk
from tkinter import filedialog, ttk

from comfyui_support_tools.applications.main_gui.ui.commander.media_commander import (
    MediaUiCommander,
)
from comfyui_support_tools.applications.main_gui.ui.processing.media_grid import MediaGrid

SORT_LABELS = {"名前": "name", "更新日時": "modified", "サイズ": "size"}
COLLECTION_LABELS = {"Library": "library", "Dataset": "dataset", "Generated": "generated"}


# {
# 責務: [MediaBrowserPanel: read-only media scanning/filter/list/grid/preview UIを構築する]
# フィールド: [commander/callbacks, query/sort/collection vars, render tokens, scheduled filter/poll timers, view widgets]
# }
class MediaBrowserPanel(ttk.Frame):
    # {
    #   責務: [__init__: media browser stateを初期化しcontrols/poll timerを起動する]
    #   処理: [default section/sort/grid modeを設定しbuild/render後query traceとasync pollを登録する]
    #   引数: [self: panel, master: parent, commander: MediaUiCommander, on_selection: selection callback, on_preview: preview callback]
    #   戻り値: [なし]
    #   副作用: [Tk widgets/variablesを作り60ms poll timerをscheduleする]
    # }
    def __init__(self, master, commander: MediaUiCommander, on_selection, on_preview):
        super().__init__(master)
        self.commander = commander
        self.on_selection, self.on_preview = on_selection, on_preview
        self.section, self.folder = "all", ""
        self.collection = tk.StringVar(self, value="Library")
        self.query = tk.StringVar(self)
        self.sort = tk.StringVar(self, value="名前")
        self.descending = tk.BooleanVar(self, value=False)
        self.mode = tk.StringVar(self, value="サムネイル")
        self.status = tk.StringVar(self)
        self.path_text = tk.StringVar(self, value="画像・動画のフォルダを選択してください")
        self._page_token = self._preview_token = 0
        self._closed = self._dirty = self._rendering = False
        self._next_render = 0.0
        self._filter_after = None
        self._build()
        self._render()
        self.query.trace_add("write", self._schedule_filter)
        self._after = self.after(60, self._poll)
        self.bind("<Destroy>", self._destroyed, add=True)

    # {
    #   責務: [_build: folder/search/sort/mode/favorite/page/table/grid controlsを配置してevent bindingする]
    #   処理: [grid/list view containersとscrollbars/status/page navigationを組み立てる]
    #   引数: [self: panel]
    #   戻り値: [None]
    #   副作用: [Tk widget tree/bindingsを構築する]
    # }
    def _build(self):
        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        ttk.Button(row, text="フォルダを開く", command=self.choose_folder).pack(side="left")
        ttk.Button(row, text="再読込", command=self.reload).pack(side="left", padx=4)
        ttk.Label(row, text="分類").pack(side="left", padx=(8, 2))
        ttk.Combobox(
            row,
            textvariable=self.collection,
            values=tuple(COLLECTION_LABELS),
            state="readonly",
            width=10,
        ).pack(side="left")
        ttk.Label(self, textvariable=self.path_text, wraplength=450).pack(anchor="w", pady=(2, 6))
        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="検索").pack(side="left")
        ttk.Entry(row, textvariable=self.query, width=16).pack(side="left", padx=4)
        sorts = ttk.Combobox(
            row, textvariable=self.sort, values=tuple(SORT_LABELS), state="readonly", width=8
        )
        sorts.pack(side="left")
        sorts.bind("<<ComboboxSelected>>", lambda _event: self.apply_query())
        ttk.Checkbutton(row, text="降順", variable=self.descending, command=self.apply_query).pack(
            side="left"
        )
        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        modes = ttk.Combobox(
            row, textvariable=self.mode, values=("サムネイル", "リスト"), state="readonly", width=12
        )
        modes.pack(side="left")
        modes.bind("<<ComboboxSelected>>", lambda _event: self._render())
        ttk.Button(row, text="★ 選択を切替", command=self.toggle_favorites).pack(
            side="left", padx=6
        )
        ttk.Label(row, text="Ctrl / Shift: 複数選択").pack(side="left")
        self.deck = ttk.Frame(self)
        self.deck.pack(fill="both", expand=True)
        self.deck.rowconfigure(0, weight=1)
        self.deck.columnconfigure(0, weight=1)
        self.grid_view = MediaGrid(self.deck, self.select)
        self.list_frame = ttk.Frame(self.deck)
        self.table = ttk.Treeview(
            self.list_frame,
            show="headings",
            selectmode="extended",
            columns=("name", "kind", "size", "modified", "collection"),
            height=8,
        )
        for key, title, width in (
            ("name", "ファイル", 200),
            ("kind", "種類", 60),
            ("size", "サイズ", 85),
            ("modified", "更新日時", 140),
            ("collection", "分類", 90),
        ):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=50, stretch=key == "name")
        self.table.grid(row=0, column=0, sticky="nsew")
        self.list_frame.rowconfigure(0, weight=1)
        self.list_frame.columnconfigure(0, weight=1)
        vertical = ttk.Scrollbar(self.list_frame, orient="vertical", command=self.table.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(self.list_frame, orient="horizontal", command=self.table.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.table.bind("<<TreeviewSelect>>", self._list_selected)
        self.table.bind("<Control-a>", self._select_all)
        row = ttk.Frame(self)
        row.pack(side="bottom", fill="x", pady=4, before=self.deck)
        self.previous = ttk.Button(row, text="← 前", command=lambda: self.move_page(-1))
        self.previous.pack(side="left")
        self.next = ttk.Button(row, text="次 →", command=lambda: self.move_page(1))
        self.next.pack(side="left", padx=4)
        self.status_label = ttk.Label(row, textvariable=self.status, wraplength=200)
        self.status_label.pack(side="left", fill="x", expand=True, padx=6)
        self.status_label.bind(
            "<Configure>",
            lambda event: self.status_label.configure(wraplength=max(100, event.width)),
        )

    # {
    #   責務: [choose_folder: user folder chooserを開き選択folderをcurrent collectionでloadする]
    #   処理: [nonempty dialog result時のみload_folderを呼ぶ]
    #   引数: [self: panel]
    #   戻り値: [None]
    #   副作用: [native directory chooserを開きscan requestを開始する]
    # }
    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self, title="画像・動画フォルダを選択")
        if folder:
            self.load_folder(folder, COLLECTION_LABELS[self.collection.get()])

    # {
    #   責務: [load_folder: path/collection stateを更新してasync scanを開始しviewをrefreshする]
    #   処理: [collection labelを同期、path text設定、commander.load後selection通知とrenderを行う]
    #   引数: [self: panel, folder: scan root, collection: collection ID]
    #   戻り値: [なし]
    #   副作用: [background scan/preview token stateとUIを更新する]
    # }
    def load_folder(self, folder: str, collection: str = "library"):
        self.folder = folder
        label = next(
            (name for name, value in COLLECTION_LABELS.items() if value == collection), None
        )
        if label:
            self.collection.set(label)
        self.path_text.set(folder)
        self.commander.load(folder, collection)
        self._notify_selection()
        self._render()

    # {
    #   責務: [reload: folderが設定済みならcurrent collectionで再scanする]
    #   処理: [current folderとcollection labelでload_folderを呼ぶ]
    #   引数: [self: panel]
    #   戻り値: [None]
    # }
    def reload(self):
        if self.folder:
            self.load_folder(self.folder, COLLECTION_LABELS[self.collection.get()])

    # {
    #   責務: [set_section: browser sectionを保存しfilter/renderを再適用する]
    #   処理: [sectionを更新してapply_queryを呼ぶ]
    #   引数: [self: panel, section: supported media section key]
    #   戻り値: [なし]
    # }
    def set_section(self, section: str):
        self.section = section
        self.apply_query()

    # {
    #   責務: [_schedule_filter: search text変更を180ms debounceして適用する]
    #   処理: [existing timerをcancelし新しいapply_query timerを設定する]
    #   引数: [self: panel, _args: Tk trace callback values]
    #   戻り値: [None]
    #   副作用: [Tk after timerを作成/取消する]
    # }
    def _schedule_filter(self, *_args):
        if self._filter_after:
            self.after_cancel(self._filter_after)
        self._filter_after = self.after(180, self.apply_query)

    # {
    #   責務: [apply_query: section/search/sort settingsをcommanderへ反映しselection/renderを同期する]
    #   処理: [pending debounceをcancelしlocalized sortをkeyへ変換してqueryを送る]
    #   引数: [self: panel]
    #   戻り値: [なし]
    #   副作用: [session filter/page/selection stateとTk viewsを更新する]
    # }
    def apply_query(self):
        if self._filter_after:
            self.after_cancel(self._filter_after)
            self._filter_after = None
        self.commander.query(
            self.section, self.query.get(), SORT_LABELS[self.sort.get()], self.descending.get()
        )
        self._notify_selection()
        self._render()

    # {
    #   責務: [move_page: requested relative pageへ移動しselection/viewを再同期する]
    #   処理: [commander.move_page後selection notify/renderを行う]
    #   引数: [self: panel, delta: previous/next page offset]
    #   戻り値: [なし]
    # }
    def move_page(self, delta: int):
        self.commander.move_page(delta)
        self._notify_selection()
        self._render()

    # {
    #   責務: [select: requested visible IDsをcanonicalizeしgrid/table/Inspectorへ同期する]
    #   処理: [commander selectionを取得してcurrent mode widgetを更新する]
    #   引数: [self: panel, keys: requested item IDs]
    #   戻り値: [None]
    #   副作用: [selection callback/preview requestを発行する]
    # }
    def select(self, keys):
        selected = self.commander.select(keys)
        canonical = tuple(item.id for item in selected)
        if self.mode.get() == "リスト" and self.table.selection() != canonical:
            self.table.selection_set(canonical)
        self.grid_view.selected = set(canonical)
        if self.mode.get() == "サムネイル":
            self.grid_view.redraw()
        self._notify_selection()

    # {
    #   責務: [_notify_selection: selection callbackとnew generation preview requestを通知する]
    #   処理: [preview tokenをincrementしselected MediaItemsをcallbackへ渡す]
    #   引数: [self: panel]
    #   戻り値: [None]
    #   副作用: [parent callbackとpreview worker requestを実行する]
    # }
    def _notify_selection(self):
        self._preview_token += 1
        self.on_selection(self.commander.selection())
        self.commander.preview(self._preview_token, 0.0)

    # {
    #   責務: [restore_selection: viewへ戻る時selection/previewを再通知する]
    #   処理: [_notify_selectionへdelegateする]
    #   引数: [self: panel]
    #   戻り値: [None]
    # }
    def restore_selection(self):
        self._notify_selection()

    # {
    #   責務: [request_preview: explicit slider fractionのpreview requestを発行する]
    #   処理: [preview tokenをincrementしてcommander.previewを呼ぶ]
    #   引数: [self: panel, fraction: normalized video position]
    #   戻り値: [None]
    #   副作用: [preview decode workerを依頼する]
    # }
    def request_preview(self, fraction: float):
        self._preview_token += 1
        self.commander.preview(self._preview_token, fraction)

    # {
    #   責務: [toggle_favorites: selection favorite stateを切替えselectionとvisible rowsを更新する]
    #   処理: [commander.toggle_favorites、selection通知、renderを順に行う]
    #   引数: [self: panel]
    #   戻り値: [None]
    # }
    def toggle_favorites(self):
        self.commander.toggle_favorites()
        self._notify_selection()
        self._render()

    # {
    #   責務: [_list_selected: user-originated Treeview selectionをcommanderへ同期する]
    #   処理: [render中/thumbnail modeは無視しcanonical ID tuple差分時のみselectする]
    #   引数: [self: panel, _event: optional tree selection event]
    #   戻り値: [None]
    # }
    def _list_selected(self, _event=None):
        if not self._rendering and self.mode.get() == "リスト":
            keys = self.table.selection()
            if keys != tuple(item.id for item in self.commander.selection()):
                self.select(keys)

    # {
    #   責務: [_select_all: current list page rowsを選びCtrl-A default behaviorを止める]
    #   処理: [Treeview childrenをselection_setする]
    #   引数: [self: panel, _event: optional key event]
    #   戻り値: ["break"]
    # }
    def _select_all(self, _event=None):
        self.table.selection_set(self.table.get_children())
        return "break"

    # {
    #   責務: [_render: current pageをgridまたはtable modeで描画しpage-scoped requestsを更新する]
    #   処理: [view/selectionを取得しmode別widgetsを描きthumbnail enqueueまたはqueued thumbnail cancelを行う]
    #   引数: [self: panel]
    #   戻り値: [None]
    #   副作用: [Tk rows/status/buttons、render flags、generation tokenを更新する]
    # }
    def _render(self):
        self._rendering = True
        before = self.commander.selection()
        items, info = self.commander.view()
        if before != self.commander.selection():
            self._notify_selection()
        selected = tuple(item.id for item in self.commander.selection())
        self._page_token += 1
        self.grid_view.grid_remove()
        self.list_frame.grid_remove()
        if self.mode.get() == "サムネイル":
            self.grid_view.grid(row=0, column=0, sticky="nsew")
            self.grid_view.render(items, selected)
            self.commander.thumbnails(self._page_token)
        else:
            self.list_frame.grid(row=0, column=0, sticky="nsew")
            self.table.delete(*self.table.get_children())
            for item in items:
                stamp = datetime.fromtimestamp(item.modified_ns / 1_000_000_000).strftime(
                    "%Y-%m-%d %H:%M"
                )
                self.table.insert(
                    "",
                    "end",
                    iid=item.id,
                    values=(item.name, item.kind, f"{item.size:,} B", stamp, item.collection),
                )
            self.table.selection_set(tuple(key for key in selected if self.table.exists(key)))
            # Cancel queued thumbnails on list mode; keep only selected preview.
            self.commander.thumbnails(self._page_token, False)
        state = "読込中…" if info["loading"] else info["message"]
        self.status.set(f"{info['total']:,} 件 / {info['page'] + 1}/{info['pages']}頁\n{state}")
        self.previous.configure(state="normal" if info["page"] > 0 else "disabled")
        self.next.configure(state="normal" if info["page"] + 1 < info["pages"] else "disabled")
        self._rendering = False
        self._dirty = False
        self._next_render = time.monotonic() + 0.25

    # {
    #   責務: [_poll: Data eventsを60msごとに取得しcurrent tokenのthumbnail/previewだけ反映する]
    #   処理: [stale tokenを無視しdirty scan stateをthrottle後renderする]
    #   引数: [self: panel]
    #   戻り値: [None。closedならreturn]
    #   副作用: [preview callback/grid、次回Tk timerを更新する]
    # }
    def _poll(self):
        if self._closed:
            return
        changed, events = self.commander.poll()
        self._dirty = self._dirty or changed
        thumbnail_changed = False
        for event in events:
            if event.kind == "thumbnail" and event.token == self._page_token and event.preview:
                if self.mode.get() == "サムネイル":
                    self.grid_view.set_preview(event.preview)
                    thumbnail_changed = True
            elif event.kind == "preview" and event.token == self._preview_token and event.preview:
                self.on_preview(event.preview)
        if thumbnail_changed:
            self.grid_view.redraw()
        if self._dirty and time.monotonic() >= self._next_render:
            self._render()
        self._after = self.after(60, self._poll)

    # {
    #   責務: [close: browser poll/filter timerをcancelしMediaCommander worker chainを閉じる]
    #   処理: [冪等にclosedを設定し存在するtimerを取り消してcommander.closeする]
    #   引数: [self: panel]
    #   戻り値: [None]
    #   副作用: [Tk callbacksとmedia workersを停止する]
    # }
    def close(self):
        if not self._closed:
            self._closed = True
            if self._filter_after:
                self.after_cancel(self._filter_after)
            self.after_cancel(self._after)
            self.commander.close()

    # {
    #   責務: [_destroyed: panel自身のDestroy event時にclose cleanupを呼ぶ]
    #   処理: [event.widget identityを確認してcloseする]
    #   引数: [self: panel, event: Tk Destroy event]
    #   戻り値: [None]
    # }
    def _destroyed(self, event):
        if event.widget is self:
            self.close()
