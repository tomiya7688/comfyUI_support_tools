import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "scripts"

from .context import *
from .context import _safe_thread
from .services import *
from .tabs.flat_file_copy import FlatFileCopyTab
from .tabs.tag_deleter import TagDeleterTab
from .tabs.tag_splitter import TagSplitterTab
from .tabs.tag_replacer import TagReplacerTab
from .tabs.text_merger import TextMergerTab
from .tabs.start_webui import StartWebUITab
from .tabs.random_image import RandomImageTab
from .tabs.random_img2img import RandomImg2ImgTab
from .tabs.folder_tagger import FolderTaggerTab
from .tabs.random_line_picker import RandomLinePickerTab
from .tabs.body_prompt import BodyPromptTab
from .tabs.check_braces import CheckBracesTab
from .tabs.generic_subprocess import GenericSubprocessTab
from .tabs.screenshot_from_movie import ScreenshotFromMovieTab
from .tabs.images_to_webp import ImagesToWebpTab
from .tabs.duplicate_line_delete import DuplicateLineDeleteTab
from .tabs.ffmpeg_repair import FfmpegRepairTab
from .tabs.zipper import ZipperTab
from .tabs.youtube_downloader import YouTubeDownloaderTab
from .tabs.video_reencoder import VideoReencoderTab
from .tabs.static_spec import StaticSpecTab
from .tabs.docstring_audit import DocstringAuditTab
from .tabs.dependency_status import DependencyStatusTab
from .tabs.ollama_prompt import OllamaPromptTab
from .tabs.touka_enhancer import ToukaEnhancerTab
from .tabs.wildcard_checker import WildcardCheckerTab
from .tabs.wildcard_move import WildcardMoveTab
from .tabs.prompt_generate import PromptGenerateTab
from .tabs.tag_to_prompt import TagToPromptTab
from .tabs.movie_to_text import MovieToTextTab
from .widgets.scrollable_tab_container import ScrollableTabContainer
from .widgets.last_settings_store import LastSettingsStore
from .widgets.tab_navigation import TabNavigation
from .widgets.dark_theme import DarkTheme

def _launch_backend_gui(backend):
    if backend not in {"a1111", "comfyui"}:
        raise ValueError(f"未対応のバックエンドです: {backend}")
    runtime_directory = COMFYUI_DIR if backend == "comfyui" else A1111_DIR
    python_candidates = (
        runtime_directory / "venv" / "Scripts" / "python.exe",
        Path(sys.executable),
    )
    python_path = next((path for path in python_candidates if path.is_file()), None)
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
    def __init__(self):
        super().__init__()
        DarkTheme().apply(self)
        self.title(f"Kadoka Tools - {BACKEND_DISPLAY_NAME} Tabbed GUI")
        self.geometry("1080x760")
        self.minsize(900, 600)
        self.last_settings_store = LastSettingsStore(RUNTIME_BACKEND)

        tab_titles = [
            (f"{BACKEND_DISPLAY_NAME}起動", StartWebUITab),
            ("random txt2img", RandomImageTab),
            ("Prompt生成", PromptGenerateTab),
            ("Random img2img", RandomImg2ImgTab),
            ("Folder Tagger", FolderTaggerTab),
            ("Random Line Picker", RandomLinePickerTab),
            ("Body Prompt", BodyPromptTab),
            ("Tag Deleter", TagDeleterTab),
            ("Tag Splitter", TagSplitterTab),
            ("Tag Replacer", TagReplacerTab),
            ("Tag to Prompt", TagToPromptTab),
            ("Flat Copy/Move", FlatFileCopyTab),
            ("Text Merger", TextMergerTab),
            ("Movie Frames", ScreenshotFromMovieTab),
            ("Movie to Text", MovieToTextTab),
            ("画像をWEBP変換", ImagesToWebpTab),
            ("重複行削除", DuplicateLineDeleteTab),
            ("ffmpeg修復", FfmpegRepairTab),
            ("Brace Check", CheckBracesTab),
            ("Wildcard Check", WildcardCheckerTab),
            ("Wildcard Move", WildcardMoveTab),
            ("Zipper", ZipperTab),
            ("YouTube Downloader", YouTubeDownloaderTab),
            ("Video Reencoder", VideoReencoderTab),
            ("静的仕様書", StaticSpecTab),
            ("Docstring検査", DocstringAuditTab),
            ("依存状態", DependencyStatusTab),
            ("Ollama Prompt", OllamaPromptTab),
            ("半透明素材強調", ToukaEnhancerTab)
        ]

        self.tab_frames = []
        self.tab_buttons = []
        self.tab_instances = []

        navigation = TabNavigation(self)
        navigation.pack(fill="x", pady=(4, 0))

        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=4, pady=4)
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        half = (len(tab_titles) + 1) // 2
        for index, (title, cls) in enumerate(tab_titles):
            try:
                frame = ScrollableTabContainer(content)
                tab = cls(frame.content)
                self.last_settings_store.restore(tab)
                tab.pack(fill="both", expand=True)
            except Exception as e:
                frame = ttk.Frame(content, padding=10)
                ttk.Label(frame, text=f"{title} の初期化に失敗しました: {type(e).__name__}: {e}").pack(anchor="w")
                tab = None
            frame.grid(row=0, column=0, sticky="nsew")
            self.tab_frames.append(frame)
            if tab is not None:
                self.tab_instances.append(tab)

            btn_parent = navigation.first_row if index < half else navigation.second_row
            btn = tk.Button(btn_parent, text=title, relief="raised", width=16, padx=4, pady=4,
                             command=lambda idx=index: self.show_tab(idx))
            btn.pack(side="left", padx=2, pady=2)
            self.tab_buttons.append(btn)

        self.current_tab_index = None
        self.show_tab(0)
        self.protocol("WM_DELETE_WINDOW", self._close)

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
