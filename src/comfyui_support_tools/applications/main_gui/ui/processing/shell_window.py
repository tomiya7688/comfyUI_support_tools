"""Five-region shell. All Tk work stays on its owning event-loop thread."""

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from comfyui_support_tools.applications.main_gui.ui.commander.navigation_commander import (
    NavigationUiCommander,
)
from comfyui_support_tools.applications.main_gui.ui.processing.library_panel import (
    LABELS,
    LibraryPanel,
)
from comfyui_support_tools.applications.main_gui.ui.processing.workspace_panel import WorkspacePanel
from comfyui_support_tools.applications.main_gui.ui.processing.media_preview_panel import (
    MediaPreviewPanel,
)
from comfyui_support_tools.applications.main_gui.ui.processing.job_queue_panel import JobQueuePanel


# {
# 責務: [ShellWindow: Tk event loop上のLibrary/Workspace/Inspector/Jobs五領域shellを構成する]
# フィールド: [navigation/workspace/panes/media preview/job panel, visibility flags, bounded log widgets]
# }
class ShellWindow(tk.Tk):
    # {
    #   責務: [__init__: five-region shellとoptional media/job componentsを構築する]
    #   処理: [menu/toolbar/paned layout/Inspector/Jobsを生成しinitial tool viewとlogを設定する]
    #   引数: [self: root window, commander: NavigationUiCommander, on_open: legacy callback, media: optional media UI API, jobs: optional job queue API]
    #   戻り値: [なし]
    #   副作用: [Tk window/widgets/event bindingsを生成しlayout callbacksをscheduleする]
    # }
    def __init__(
        self,
        commander: NavigationUiCommander,
        on_open: Callable[[str], None],
        media=None,
        jobs=None,
    ):
        super().__init__()
        self.commander = commander
        self.on_open = on_open
        self.jobs_commander = jobs
        self.media_selection = ()
        self.title("Kadoka Tools — Workspace Preview")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.query = tk.StringVar(self)
        self.category = tk.StringVar(self, value="すべて")
        self.visible = {
            name: tk.BooleanVar(self, value=True) for name in ("library", "inspector", "jobs")
        }
        self._build_menu()
        self._build_toolbar()
        self.vertical = ttk.Panedwindow(self, orient="vertical")
        self.vertical.pack(fill="both", expand=True, padx=8, pady=8)
        self._initial_layout_pending = True
        self.vertical.bind("<Configure>", self._initialize_layout)
        self.horizontal = ttk.Panedwindow(self.vertical, orient="horizontal")
        self.library = LibraryPanel(self.horizontal, self.select_section)
        self.workspace = WorkspacePanel(
            self.horizontal,
            self.open_tool,
            self.inspect_tool,
            media,
            self.inspect_media,
            self.render_media_preview,
        )
        self.inspector = ttk.Frame(self.horizontal, padding=12, width=245)
        inspector_canvas = tk.Canvas(self.inspector, highlightthickness=0, width=215)
        inspector_scroll = ttk.Scrollbar(
            self.inspector, orient="vertical", command=inspector_canvas.yview
        )
        inspector_scroll.pack(side="right", fill="y")
        inspector_canvas.pack(side="left", fill="both", expand=True)
        inspector_canvas.configure(yscrollcommand=inspector_scroll.set)
        inspector_body = ttk.Frame(inspector_canvas)
        inspector_window = inspector_canvas.create_window(0, 0, window=inspector_body, anchor="nw")
        inspector_body.bind(
            "<Configure>",
            lambda _event: inspector_canvas.configure(scrollregion=inspector_canvas.bbox("all")),
        )
        inspector_canvas.bind(
            "<Configure>",
            lambda event: inspector_canvas.itemconfigure(inspector_window, width=event.width),
        )
        ttk.Label(inspector_body, text="INSPECTOR", font=("TkDefaultFont", 11, "bold")).pack(
            anchor="w"
        )
        self.inspector_text = ttk.Label(
            inspector_body,
            text="メディアInspectorは準備中 (#220)\n旧ツールを選ぶと移行先を表示します。",
            wraplength=205,
            justify="left",
        )
        self.inspector_text.pack(anchor="w", pady=12)
        self.media_preview = MediaPreviewPanel(inspector_body, self.seek_media)
        if media is not None:
            self.inspector_text.configure(text="メディアを選択すると情報を表示します。")
            self.media_preview.pack(fill="x")
        self.jobs = ttk.Frame(self.vertical, padding=8, height=210)
        self.job_tabs = ttk.Notebook(self.jobs)
        self.job_tabs.pack(fill="both", expand=True)
        job_page = ttk.Frame(self.job_tabs, padding=4)
        log_page = ttk.Frame(self.job_tabs, padding=4)
        self.job_tabs.add(job_page, text="Jobs")
        self.job_tabs.add(log_page, text="UI Log")
        self.log = ScrolledText(log_page, height=5, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)
        self.job_panel = None
        if jobs is not None:
            self.job_panel = JobQueuePanel(job_page, jobs, self.append_log)
            self.job_panel.pack(fill="both", expand=True)
        else:
            ttk.Label(job_page, text="Job Queue controller未接続").pack(anchor="w")
        self.horizontal.add(self.library, weight=0)
        self.horizontal.add(self.workspace, weight=1)
        self.horizontal.add(self.inspector, weight=0)
        self.vertical.add(self.horizontal, weight=1)
        self.vertical.add(self.jobs, weight=0)
        self.workspace.render(self.commander.visible_tools())
        self.query.trace_add("write", lambda *_args: self.filter_tools())
        self.update_idletasks()
        self._reset_sashes()
        self.append_log("新GUIを開きました。バックエンドの起動・接続は行いません。")

    # {
    #   責務: [_build_menu: File/ExitとLibrary/Inspector/Jobs visibility menuを作る]
    #   処理: [pane checkbuttonsをset_pane_visible callbackへbindする]
    #   引数: [self: window]
    #   戻り値: [None]
    #   副作用: [Tk Menuを構築しroot menuへ設定する]
    # }
    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="旧UIを開く", command=self.open_legacy_home)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self.destroy)
        menu.add_cascade(label="ファイル", menu=file_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        for name, label in (
            ("library", "Library"),
            ("inspector", "Inspector"),
            ("jobs", "Jobs / Log"),
        ):
            view_menu.add_checkbutton(
                label=label,
                variable=self.visible[name],
                command=lambda key=name: self.set_pane_visible(key, self.visible[key].get()),
            )
        menu.add_cascade(label="表示", menu=view_menu)
        self.configure(menu=menu)

    # {
    #   責務: [_build_toolbar: branding、legacy navigation、tool query/category controlsを配置する]
    #   処理: [commander categoriesをcomboboxに供給しsearch/category eventsをbindする]
    #   引数: [self: window]
    #   戻り値: [None]
    #   副作用: [Tk toolbar/filter widgetsとkey bindingを生成する]
    # }
    def _build_toolbar(self) -> None:
        self.toolbar = ttk.Frame(self, padding=(16, 10))
        self.toolbar.pack(fill="x")
        ttk.Label(self.toolbar, text="KADOKA TOOLS", font=("TkDefaultFont", 15, "bold")).pack(
            side="left"
        )
        ttk.Label(self.toolbar, text="Workspace Preview / 段階移行中").pack(side="left", padx=18)
        ttk.Button(self.toolbar, text="旧UIを開く", command=self.open_legacy_home).pack(
            side="right"
        )
        filters = ttk.Frame(self, padding=(16, 4))
        filters.pack(fill="x")
        ttk.Label(filters, text="機能検索").pack(side="left")
        self.search = ttk.Entry(filters, textvariable=self.query, width=26)
        self.search.pack(side="left", padx=8)
        categories = ttk.Combobox(
            filters,
            textvariable=self.category,
            values=("すべて", *self.commander.categories()),
            state="readonly",
            width=16,
        )
        categories.pack(side="left")
        categories.bind("<<ComboboxSelected>>", lambda _event: self.filter_tools())
        ttk.Label(filters, text="Backend API: 未確認 / 自動起動なし").pack(side="right")
        self.bind("<Control-f>", lambda _event: self.search.focus_set())

    # {
    #   責務: [select_section: Library sectionを切替えWorkspace/title/media filter/Inspectorを同期する]
    #   処理: [ToolEntryをrenderしselectionをclearし、mediaがあればmedia viewと同sectionを選ぶ]
    #   引数: [self: window, section: supported Library section key]
    #   戻り値: [None]
    #   副作用: [workspace/media/Inspector stateとlogを更新する]
    # }
    def select_section(self, section: str) -> None:
        tools = self.commander.select_section(section)
        self.workspace.title.configure(text=LABELS[section])
        self.workspace.render(tools)
        self.inspect_tool("")
        if self.workspace.media is not None:
            self.workspace.show_media()
            self.workspace.media.set_section(section)
        self.append_log(f"Library: {LABELS[section]}")

    # {
    #   責務: [filter_tools: query/categoryに一致するlegacy tool listをrenderしtool Inspector selectionをclearする]
    #   処理: [tools viewへ切替え、'すべて' categoryをempty filterに変換する]
    #   引数: [self: window]
    #   戻り値: [None]
    # }
    def filter_tools(self) -> None:
        self.workspace.show_tools()
        category = "" if self.category.get() == "すべて" else self.category.get()
        self.workspace.render(self.commander.filter_tools(self.query.get(), category))
        self.inspect_tool("")

    # {
    #   責務: [inspect_tool: tools mode時selected ToolEntryのmigration destination説明をInspectorへ表示する]
    #   処理: [media modeではno-op、tools modeではpreview clear後visible registryからlabel/categoryを探す]
    #   引数: [self: window, tool_id: selected tool identifier]
    #   戻り値: [None]
    #   副作用: [Inspector text/preview widgetsを更新する]
    # }
    def inspect_tool(self, tool_id: str) -> None:
        if self.workspace.mode != "tools":
            return
        self.media_preview.pack_forget()
        self.media_preview.select(())
        tool = next((item for item in self.commander.visible_tools() if item.id == tool_id), None)
        text = (
            f"{tool.label}\n\nカテゴリ: {tool.category}\n旧UIで開きます。\nここから処理は実行しません。"
            if tool
            else "メディアInspectorは準備中 (#220)\n旧ツールを選ぶと移行先を表示します。"
        )
        self.inspector_text.configure(text=text)

    # {
    #   責務: [inspect_media: media mode時selected MediaItemsを保存しpreview/Inspector textを同期する]
    #   処理: [MediaItem tupleを保持し先頭item metadataを説明、selection-changed eventをtailに送る]
    #   引数: [self: window, items: selected MediaItem sequence]
    #   戻り値: [None]
    #   副作用: [preview/Inspector widgetsを更新しvirtual eventを発行する]
    # }
    def inspect_media(self, items) -> None:
        # Stable MediaItem tuple is also the contract for the upcoming Action UI.
        self.media_selection = tuple(items) if self.workspace.mode == "media" else ()
        self.media_preview.select(self.media_selection)
        if self.workspace.mode == "media":
            self.media_preview.pack(fill="x")
            text = "メディア未選択"
            if items:
                item = items[0]
                text = (
                    f"{len(items)} 件選択\n{item.name}\n{item.kind} / {item.size:,} B\n"
                    f"{item.path}\n\n表示のみ。編集Actionは準備中 (#220)。"
                )
            self.inspector_text.configure(text=text)
        self.event_generate("<<MediaSelectionChanged>>", when="tail")

    # {
    #   責務: [render_media_preview: media mode時だけMediaPreviewをInspector previewへ描画する]
    #   処理: [tools viewではstale media previewを表示しない]
    #   引数: [self: window, preview: MediaPreview]
    #   戻り値: [None]
    # }
    def render_media_preview(self, preview) -> None:
        if self.workspace.mode == "media":
            self.media_preview.render(preview)

    # {
    #   責務: [seek_media: media browserがあればslider fractionのpreview requestを依頼する]
    #   処理: [workspace.media.request_previewへfractionを渡す]
    #   引数: [self: window, fraction: normalized seek position]
    #   戻り値: [None]
    # }
    def seek_media(self, fraction: float) -> None:
        if self.workspace.media is not None:
            self.workspace.media.request_preview(fraction)

    # {
    #   責務: [open_tool: valid selected toolをrecentへ記録してlegacy callbackへ渡す]
    #   処理: [commander.request_open後on_openを実行しknown filesystem errorsをlogする]
    #   引数: [self: window, tool_id: selected tool ID]
    #   戻り値: [None]
    #   エラー: [ValueError/OSErrorをlogに変換する]
    #   副作用: [on_open callbackまたはlog callbackを呼ぶ]
    # }
    def open_tool(self, tool_id: str) -> None:
        try:
            target = self.commander.request_open(tool_id)
            self.on_open(target)
        except (ValueError, OSError) as exc:
            self.append_log(f"旧UIを開けません: {exc}")

    # {
    #   責務: [open_legacy_home: legacy UI homeへのopen requestを発行する]
    #   処理: [empty destination stringでon_open callbackを呼ぶ]
    #   引数: [self: window]
    #   戻り値: [None]
    #   副作用: [on_open("")を呼ぶ]
    # }
    def open_legacy_home(self) -> None:
        self.on_open("")

    # {
    #   責務: [set_pane_visible: known paneをhorizontal/vertical Panedwindowへ追加または除去する]
    #   処理: [pane nameを検証しvisibilityを同期、visibilityが変わればsash resetをidleにscheduleする]
    #   引数: [self: window, name: library/inspector/jobs pane, visible: desired visibility]
    #   戻り値: [None]
    #   エラー: [ValueError: pane name未登録]
    #   副作用: [Tk paned layoutとafter_idle callbackを変更する]
    # }
    def set_pane_visible(self, name: str, visible: bool) -> None:
        if name not in self.visible:
            raise ValueError(f"Unknown pane: {name}")
        self.visible[name].set(visible)
        pane = getattr(self, name)
        parent = self.vertical if name == "jobs" else self.horizontal
        present = str(pane) in parent.panes()
        if present and not visible:
            parent.forget(pane)
        elif not present and visible:
            parent.insert(0 if name == "library" else "end", pane, weight=0)
        self.after_idle(self._reset_sashes)

    # {
    #   責務: [_initialize_layout: negotiated window sizeが十分な後初回sash positionをresetする]
    #   処理: [initial pendingかつwidth>700/height>400の時だけfirst layoutを確定する]
    #   引数: [self: window, event: vertical Panedwindow Configure event]
    #   戻り値: [None]
    #   副作用: [idle callbackでsash positionsを設定する]
    # }
    def _initialize_layout(self, event: tk.Event) -> None:
        # On Windows geometry is negotiated after construction. Never freeze the
        # initial sash positions while a Panedwindow still measures 1 x 1.
        if self._initial_layout_pending and event.width > 700 and event.height > 400:
            self._initial_layout_pending = False
            self.after_idle(self._reset_sashes)

    # {
    #   責務: [_reset_sashes: visible vertical/horizontal pane proportionsをlayout sizeに合わせて再設定する]
    #   処理: [jobs paneを先に設定しidle geometry更新後library/inspector dividerを調整する]
    #   引数: [self: window]
    #   戻り値: [None]
    #   副作用: [Tk layout measurementとsash positionsを更新する]
    # }
    def _reset_sashes(self) -> None:
        # Size the outer pane first; the horizontal pane may still be unmapped.
        if self.visible["jobs"].get():
            self.vertical.sashpos(0, max(300, self.vertical.winfo_height() - 210))
        self.update_idletasks()
        if self.visible["library"].get():
            self.horizontal.sashpos(0, 210)
        if self.visible["inspector"].get():
            self.horizontal.sashpos(
                len(self.horizontal.panes()) - 2, max(420, self.horizontal.winfo_width() - 245)
            )

    # {
    #   責務: [append_log: UI logへmessageを追加し200行を超えたら最古行をtrimする]
    #   処理: [Textを一時enableしappend/scroll後disabledへ戻す]
    #   引数: [self: window, message: log text]
    #   戻り値: [None]
    #   副作用: [Tk Text widgetを変更する]
    # }
    def append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 200:
            self.log.delete("1.0", "2.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    # {
    #   責務: [destroy: child job panelとshared jobs commanderを閉じてroot Tk windowを破棄する]
    #   処理: [optional resourcesを存在時closeしてsuper.destroyへ委譲する]
    #   引数: [self: window]
    #   戻り値: [None]
    #   副作用: [timers/runtime/Tk resourcesを終了する]
    # }
    def destroy(self) -> None:
        if getattr(self, "job_panel", None) is not None:
            self.job_panel.close()
        if getattr(self, "jobs_commander", None) is not None:
            self.jobs_commander.close()
        super().destroy()
