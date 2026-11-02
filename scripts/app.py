import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

if __package__ in (None, ""):
    application_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(application_root))
    sys.path.insert(0, str(application_root / "src"))
    __package__ = "scripts"

from .context import (
    BACKEND_DISPLAY_NAME,
    CHECKPOINTS_DIR,
    SD_ROOT,
    USER_INPUT_DIR,
    WILDCARDS_DIR,
    configured_backend_runtime_directory,
    create_configured_last_settings_store,
)
from .runtime_python import venv_python
from .tool_registry import TOOL_REGISTRY
from .widgets.dark_theme import DarkTheme
from .widgets.scrollable_tab_container import ScrollableTabContainer
from .widgets.tab_navigation import TabNavigation
from .widgets.tk_tab_settings_adapter import TkTabSettingsAdapter


def _launch_backend_gui(backend):
    runtime_directory = configured_backend_runtime_directory(backend)
    python_path = venv_python(runtime_directory / "venv")
    if python_path is None:
        raise FileNotFoundError(f"GUI起動用Pythonがありません: {runtime_directory}")

    environment = os.environ.copy()
    environment["KADOKA_TOOLS_BACKEND"] = backend
    creationflags = 0x00000200 if os.name == "nt" else 0
    return subprocess.Popen(
        [str(python_path), str(Path(__file__).resolve()), "--backend", backend],
        cwd=str(SD_ROOT),
        env=environment,
        creationflags=creationflags,
    )


def show_backend_selector():
    selector = tk.Tk()
    DarkTheme().apply(selector)
    selector.title("Kadoka Tools - 生成バックエンド選択")
    selector.geometry("520x250")
    selector.resizable(False, False)

    frame = ttk.Frame(selector, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(
        frame,
        text="生成に使うバックエンドを選んでください",
        font=("TkDefaultFont", 13, "bold"),
    ).pack(pady=(0, 14))
    status = tk.StringVar(value=f"checkpoint: {CHECKPOINTS_DIR}\nwildcard: {WILDCARDS_DIR}")

    def choose(backend):
        try:
            _launch_backend_gui(backend)
        except Exception as exc:
            status.set(f"起動エラー: {type(exc).__name__}: {exc}")
            return
        selector.destroy()

    ttk.Button(
        frame,
        text="WebUI1111 で開く",
        command=lambda: choose("a1111"),
    ).pack(fill="x", pady=4)
    ttk.Button(
        frame,
        text="ComfyUI で開く",
        command=lambda: choose("comfyui"),
    ).pack(fill="x", pady=4)
    ttk.Label(frame, textvariable=status, justify="left", wraplength=475).pack(
        anchor="w", pady=(14, 0)
    )
    selector.mainloop()


class TabbedToolsApp(tk.Tk):
    # {
    #   責務: [__init__: Tabbed Tools GUIと全tabを初期化する]
    #   処理: [user_data pathをcomposition rootで解決し, Tk adapterと純Python settings storeを接続する]
    #   引数: [self: application window]
    #   戻り値: []
    # }
    def __init__(self):
        super().__init__()
        DarkTheme().apply(self)
        self.title(f"Kadoka Tools - {BACKEND_DISPLAY_NAME} Tabbed GUI")
        self.geometry("1080x760")
        self.minsize(900, 600)
        settings_path = USER_INPUT_DIR / "config" / "common" / "last_settings.json"
        self.last_settings_store = TkTabSettingsAdapter(
            create_configured_last_settings_store(settings_path)
        )

        tool_descriptors = TOOL_REGISTRY.descriptors

        self.tab_frames = []
        self.tab_buttons = []
        self.tab_instances = []

        navigation = TabNavigation(self)
        navigation.pack(fill="x", pady=(4, 0))

        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=4, pady=4)
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        half = (len(tool_descriptors) + 1) // 2
        for index, descriptor in enumerate(tool_descriptors):
            title = descriptor.label.format(backend=BACKEND_DISPLAY_NAME)
            try:
                frame = ScrollableTabContainer(content)
                component = TOOL_REGISTRY.load_implementation(descriptor)
                tab = component(frame.content)
                self.last_settings_store.restore(tab)
                tab.pack(fill="both", expand=True)
            except Exception as e:
                frame = ttk.Frame(content, padding=10)
                ttk.Label(
                    frame, text=f"{title} の初期化に失敗しました: {type(e).__name__}: {e}"
                ).pack(anchor="w")
                tab = None
            frame.grid(row=0, column=0, sticky="nsew")
            self.tab_frames.append(frame)
            if tab is not None:
                self.tab_instances.append(tab)

            btn_parent = navigation.first_row if index < half else navigation.second_row
            btn = tk.Button(
                btn_parent,
                text=title,
                relief="raised",
                width=16,
                padx=4,
                pady=4,
                command=lambda idx=index: self.show_tab(idx),
            )
            btn.pack(side="left", padx=2, pady=2)
            self.tab_buttons.append(btn)

        self.current_tab_index = None
        self.show_tab(0)
        self.protocol("WM_DELETE_WINDOW", self._close)

    # {
    #   責務: [_close: GUI終了前にtab設定を保存してwindowを閉じる]
    #   処理: [Tk adapterへtab一覧を渡し, 保存エラー後もwindow破棄を続ける]
    #   引数: [self: application window]
    #   戻り値: []
    # }
    def _close(self):
        try:
            self.last_settings_store.save(self.tab_instances)
        except OSError:
            pass
        self.destroy()

    def show_tab(self, index: int):
        if self.current_tab_index is not None:
            self.tab_buttons[self.current_tab_index].config(relief="raised")
        self.tab_frames[index].tkraise()
        self.tab_buttons[index].config(relief="sunken")
        self.current_tab_index = index


def main():
    app = TabbedToolsApp()
    app.mainloop()


if __name__ == "__main__":
    main()
