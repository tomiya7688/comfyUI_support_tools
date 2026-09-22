"""Five-region shell. All Tk work stays on its owning event-loop thread."""
from collections.abc import Callable
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from comfyui_support_tools.applications.main_gui.ui.commander.navigation_commander import NavigationUiCommander
from comfyui_support_tools.applications.main_gui.ui.processing.library_panel import LABELS, LibraryPanel
from comfyui_support_tools.applications.main_gui.ui.processing.workspace_panel import WorkspacePanel


class ShellWindow(tk.Tk):
    def __init__(self, commander: NavigationUiCommander, on_open: Callable[[str], None]):
        super().__init__()
        self.commander = commander
        self.on_open = on_open
        self.title("Kadoka Tools — Workspace Preview")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.query = tk.StringVar(self)
        self.category = tk.StringVar(self, value="すべて")
        self.visible = {name: tk.BooleanVar(self, value=True) for name in ("library", "inspector", "jobs")}
        self._build_menu()
        self._build_toolbar()
        self.vertical = ttk.Panedwindow(self, orient="vertical")
        self.vertical.pack(fill="both", expand=True, padx=8, pady=8)
        self._initial_layout_pending = True
        self.vertical.bind("<Configure>", self._initialize_layout)
        self.horizontal = ttk.Panedwindow(self.vertical, orient="horizontal")
        self.library = LibraryPanel(self.horizontal, self.select_section)
        self.workspace = WorkspacePanel(self.horizontal, self.open_tool, self.inspect_tool)
        self.inspector = ttk.Frame(self.horizontal, padding=12, width=245)
        ttk.Label(self.inspector, text="INSPECTOR", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.inspector_text = ttk.Label(self.inspector, text="メディアInspectorは準備中 (#220)\n旧ツールを選ぶと移行先を表示します。", wraplength=205, justify="left")
        self.inspector_text.pack(anchor="w", pady=12)
        self.jobs = ttk.Frame(self.vertical, padding=8, height=150)
        ttk.Label(self.jobs, text="JOBS / LOG — Job Queueは準備中 (#221)、下は画面操作ログです。").pack(anchor="w")
        self.log = ScrolledText(self.jobs, height=5, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, pady=(6, 0))
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

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="旧UIを開く", command=self.open_legacy_home)
        file_menu.add_separator()
        file_menu.add_command(label="終了", command=self.destroy)
        menu.add_cascade(label="ファイル", menu=file_menu)
        view_menu = tk.Menu(menu, tearoff=False)
        for name, label in (("library", "Library"), ("inspector", "Inspector"), ("jobs", "Jobs / Log")):
            view_menu.add_checkbutton(label=label, variable=self.visible[name], command=lambda key=name: self.set_pane_visible(key, self.visible[key].get()))
        menu.add_cascade(label="表示", menu=view_menu)
        self.configure(menu=menu)

    def _build_toolbar(self) -> None:
        self.toolbar = ttk.Frame(self, padding=(16, 10))
        self.toolbar.pack(fill="x")
        ttk.Label(self.toolbar, text="KADOKA TOOLS", font=("TkDefaultFont", 15, "bold")).pack(side="left")
        ttk.Label(self.toolbar, text="Workspace Preview / 段階移行中").pack(side="left", padx=18)
        ttk.Button(self.toolbar, text="旧UIを開く", command=self.open_legacy_home).pack(side="right")
        filters = ttk.Frame(self, padding=(16, 4))
        filters.pack(fill="x")
        ttk.Label(filters, text="機能検索").pack(side="left")
        self.search = ttk.Entry(filters, textvariable=self.query, width=26)
        self.search.pack(side="left", padx=8)
        categories = ttk.Combobox(filters, textvariable=self.category, values=("すべて", *self.commander.categories()), state="readonly", width=16)
        categories.pack(side="left")
        categories.bind("<<ComboboxSelected>>", lambda _event: self.filter_tools())
        ttk.Label(filters, text="Backend API: 未確認 / 自動起動なし").pack(side="right")
        self.bind("<Control-f>", lambda _event: self.search.focus_set())

    def select_section(self, section: str) -> None:
        tools = self.commander.select_section(section)
        self.workspace.title.configure(text=LABELS[section])
        self.workspace.render(tools)
        self.inspect_tool("")
        self.append_log(f"Library: {LABELS[section]}")

    def filter_tools(self) -> None:
        category = "" if self.category.get() == "すべて" else self.category.get()
        self.workspace.render(self.commander.filter_tools(self.query.get(), category))
        self.inspect_tool("")

    def inspect_tool(self, tool_id: str) -> None:
        tool = next((item for item in self.commander.visible_tools() if item.id == tool_id), None)
        text = (f"{tool.label}\n\nカテゴリ: {tool.category}\n旧UIで開きます。\nここから処理は実行しません。" if tool else "メディアInspectorは準備中 (#220)\n旧ツールを選ぶと移行先を表示します。")
        self.inspector_text.configure(text=text)

    def open_tool(self, tool_id: str) -> None:
        try:
            target = self.commander.request_open(tool_id)
            self.on_open(target)
        except (ValueError, OSError) as exc:
            self.append_log(f"旧UIを開けません: {exc}")

    def open_legacy_home(self) -> None:
        self.on_open("")

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

    def _initialize_layout(self, event: tk.Event) -> None:
        # On Windows geometry is negotiated after construction. Never freeze the
        # initial sash positions while a Panedwindow still measures 1 x 1.
        if self._initial_layout_pending and event.width > 700 and event.height > 400:
            self._initial_layout_pending = False
            self.after_idle(self._reset_sashes)

    def _reset_sashes(self) -> None:
        # Size the outer pane first; the horizontal pane may still be unmapped.
        if self.visible["jobs"].get():
            self.vertical.sashpos(0, max(300, self.vertical.winfo_height() - 160))
        self.update_idletasks()
        if self.visible["library"].get():
            self.horizontal.sashpos(0, 210)
        if self.visible["inspector"].get():
            self.horizontal.sashpos(len(self.horizontal.panes()) - 2, max(420, self.horizontal.winfo_width() - 245))

    def append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 200:
            self.log.delete("1.0", "2.0")
        self.log.see("end")
        self.log.configure(state="disabled")
