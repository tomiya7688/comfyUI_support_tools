from ..context import *
from ..context import _safe_thread
from ..services import LogBox, LabeledPathRow
from ..backend.process_cpu_limiter import ProcessCpuLimiter
from ..widgets.preset_store import PresetStore


class YouTubeDownloaderTab(ttk.Frame):
    """URLリストからYouTube動画をダウンロードするタブ。"""

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.process = None
        self.preset_store = PresetStore("youtube_downloader")
        self.preset_name = tk.StringVar()
        self.url_file = tk.StringVar(value=str(YOUTUBE_DOWNLOADER_DIR / "url_list.txt"))
        self.output_dir = tk.StringVar(value=r"J:\videos\ぷりんちゃん")
        self.max_height = tk.StringVar(value="")
        self.cpu_cores = tk.StringVar()
        self.remove_downloaded = tk.BooleanVar(value=False)
        self._build()

    def _build(self):
        ttk.Label(self, text="URL以外の行（コメント・空行を含む）は自動的に無視します。").pack(anchor="w", pady=(0, 6))
        LabeledPathRow(self, "URLリスト", self.url_file, mode="file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=3)
        LabeledPathRow(self, "出力先", self.output_dir, mode="dir").pack(fill="x", pady=3)
        row = ttk.Frame(self); row.pack(fill="x", pady=3)
        ttk.Label(row, text="最大縦解像度", width=16).pack(side="left")
        ttk.Entry(row, textvariable=self.max_height, width=12).pack(side="left")
        ttk.Label(row, text="（空欄 = 制限なし）").pack(side="left", padx=6)
        cpu_row = ttk.Frame(self); cpu_row.pack(fill="x", pady=3)
        ttk.Label(cpu_row, text="使用CPU論理数", width=16).pack(side="left")
        ttk.Entry(cpu_row, textvariable=self.cpu_cores, width=12).pack(side="left")
        ttk.Label(cpu_row, text="（空欄 = 制限なし）").pack(side="left", padx=6)
        ttk.Checkbutton(self, text="ダウンロード後、URLリストから処理済みURLを削除（URL以外の行も削除）", variable=self.remove_downloaded).pack(anchor="w", pady=4)
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="ダウンロード開始", command=self.start).pack(side="left", padx=4)
        ttk.Button(buttons, text="停止", command=self.stop).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16,4)); self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left"); ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4); ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"url_file": self.url_file.get(), "output_dir": self.output_dir.get(), "max_height": self.max_height.get(), "cpu_cores": self.cpu_cores.get(), "remove_downloaded": self.remove_downloaded.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get()); self.url_file.set(values.get("url_file", self.url_file.get())); self.output_dir.set(values.get("output_dir", self.output_dir.get())); self.max_height.set(values.get("max_height", self.max_height.get())); self.cpu_cores.set(values.get("cpu_cores", self.cpu_cores.get())); self.remove_downloaded.set(values.get("remove_downloaded", self.remove_downloaded.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    def start(self):
        if self.process and self.process.poll() is None:
            self.logbox.log("実行中です。停止してから再開してください。"); return
        url_path = Path(self.url_file.get()).expanduser()
        out_path = Path(self.output_dir.get()).expanduser()
        if not url_path.is_file():
            self.logbox.log(f"URLリストが見つかりません: {url_path}"); return
        cpu_cores = self.cpu_cores.get().strip()
        try:
            cpu_count = ProcessCpuLimiter.core_count(cpu_cores)
        except ValueError:
            self.logbox.log(f"使用CPU論理数には数値を指定してください: {cpu_cores}"); return
        python_path = YOUTUBE_DOWNLOADER_DIR / "venv" / "Scripts" / "python.exe"
        if not python_path.is_file(): python_path = Path(sys.executable)
        command = [str(python_path), str(YOUTUBE_DOWNLOADER_DIR / "youtube_dl.py"), "-i", str(url_path), "-o", str(out_path)]
        if self.max_height.get().strip(): command += ["--max-height", self.max_height.get().strip()]
        if self.remove_downloaded.get(): command += ["--remove-downloaded"]
        self.logbox.log("CPU制限: なし" if cpu_count is None else f"CPU制限: 論理CPU 0-{cpu_count - 1}")
        def worker():
            try:
                self.process = subprocess.Popen(command, cwd=str(YOUTUBE_DOWNLOADER_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                self.logbox.log(ProcessCpuLimiter.apply(self.process.pid, cpu_cores))
                for line in self.process.stdout or []: self.logbox.log(line.rstrip())
                code = self.process.wait(); self.logbox.log(f"終了しました (code={code})")
            except Exception as exc: self.logbox.log(f"起動エラー: {exc}")
        _safe_thread(self.logbox, worker)

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate(); self.logbox.log("停止要求を送信しました")
