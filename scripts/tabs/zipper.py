from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

# ``from ..context import *`` intentionally omits private names such as
# ``_HAS_PSUTIL``.  Import the optional dependency explicitly so the worker
# thread can evaluate the CPU-affinity branch without a NameError.
try:
    import psutil  # type: ignore[import-not-found]

    _HAS_PSUTIL = True
except Exception:
    psutil = None
    _HAS_PSUTIL = False


# {
#   責務: [ZipperTab: 7-Zip archive creation, split size, CPU/priority settings, and presetsを管理するtab]
#   処理: [create source/destination/tool/options controls and process archives]
#   フィールド: [input_dir, output_dir, seven_zip, split_size, max_cpu_percent, priority_mode, preset_store, preset_name, logbox]
# }
class ZipperTab(ttk.Frame):
    DEFAULT_INPUT_DIR = USER_PATHS["zipper_input_dir"]
    DEFAULT_OUTPUT_DIR = USER_PATHS["zipper_output_dir"]
    DEFAULT_SEVEN_ZIP = USER_PATHS["seven_zip_exe"]
    DEFAULT_SPLIT_SIZE = "3G"
    DEFAULT_MAX_CPU_PERCENT = 10
    DEFAULT_PRIORITY_MODE = "below_normal"

    # {
    #   責務: [__init__: archive paths, split/CPU/priority settings, and presetsを初期化する]
    #   処理: [initialize Tk variables and build controls]
    #   引数: [master]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar(value=self.DEFAULT_INPUT_DIR)
        self.output_dir = tk.StringVar(value=self.DEFAULT_OUTPUT_DIR)
        self.seven_zip = tk.StringVar(value=self.DEFAULT_SEVEN_ZIP)
        self.split_size = tk.StringVar(value=self.DEFAULT_SPLIT_SIZE)
        self.max_cpu_percent = tk.IntVar(value=self.DEFAULT_MAX_CPU_PERCENT)
        self.priority_mode = tk.StringVar(value=self.DEFAULT_PRIORITY_MODE)
        self.preset_store = PresetStore("zipper")
        self.preset_name = tk.StringVar()
        self._build()

    # {
    #   責務: [_build: input/output/tool chooser, archive options, and preset UIを構築する]
    #   処理: [compose controls and refresh saved preset names]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _build(self):
        # 入力フォルダ
        LabeledPathRow(self, "入力フォルダ", self.input_dir, mode="dir").pack(fill="x", pady=4)
        # 出力フォルダ
        LabeledPathRow(self, "出力フォルダ", self.output_dir, mode="dir").pack(fill="x", pady=4)
        # 7-Zip パス
        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="7-Zip パス", width=22).pack(side="left", padx=(0, 6))
        ttk.Entry(row, textvariable=self.seven_zip).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="参照", command=self.choose_seven_zip).pack(side="left", padx=(6, 0))

        # 設定
        settings = ttk.LabelFrame(self, text="設定", padding=8)
        settings.pack(fill="x", pady=6)
        ttk.Label(settings, text="分割サイズ").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(settings, textvariable=self.split_size, width=10).grid(
            row=0, column=1, sticky="w", padx=4, pady=3
        )
        ttk.Label(settings, text="Max CPU %").grid(row=1, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(settings, textvariable=self.max_cpu_percent, width=10).grid(
            row=1, column=1, sticky="w", padx=4, pady=3
        )
        ttk.Label(settings, text="優先度").grid(row=2, column=0, sticky="w", padx=4, pady=3)
        ttk.Combobox(
            settings,
            textvariable=self.priority_mode,
            values=["idle", "below_normal", "normal"],
            state="readonly",
        ).grid(row=2, column=1, sticky="w", padx=4, pady=3)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="圧縮開始", command=self.run_thread).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    # {
    #   責務: [_refresh_preset_choices: preset dropdownをavailable namesで更新する]
    #   処理: [configure values from PresetStore]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   責務: [save_preset: archive operation optionsをpresetへ保存する]
    #   処理: [persist paths, split size, CPU percent, and priority]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def save_preset(self):
        try:
            values = {
                "input_dir": self.input_dir.get(),
                "output_dir": self.output_dir.get(),
                "seven_zip": self.seven_zip.get(),
                "split_size": self.split_size.get(),
                "max_cpu_percent": self.max_cpu_percent.get(),
                "priority_mode": self.priority_mode.get(),
            }
            path = self.preset_store.save(self.preset_name.get(), values)
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   責務: [load_preset: selected presetからarchive settingsを復元する]
    #   処理: [restore values into Tk variables and report outcome]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.input_dir.set(values.get("input_dir", self.input_dir.get()))
            self.output_dir.set(values.get("output_dir", self.output_dir.get()))
            self.seven_zip.set(values.get("seven_zip", self.seven_zip.get()))
            self.split_size.set(str(values.get("split_size", self.split_size.get())))
            self.max_cpu_percent.set(int(values.get("max_cpu_percent", self.max_cpu_percent.get())))
            self.priority_mode.set(values.get("priority_mode", self.priority_mode.get()))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   責務: [choose_seven_zip: 7z.exeをfile dialogで選択する]
    #   処理: [show executable chooser and update path if selected]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def choose_seven_zip(self):
        path = filedialog.askopenfilename(filetypes=[("7z.exe", "7z.exe"), ("All files", "*.*")])
        if path:
            self.seven_zip.set(path)

    # {
    #   責務: [run_thread: archive preparationをdaemon worker threadで開始する]
    #   処理: [spawn start callback]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def run_thread(self):
        threading.Thread(target=self.start, daemon=True).start()

    # {
    #   責務: [start: input/output and 7-Zip settingsを検証してcompressionを開始する]
    #   処理: [validate directories and executable, create destination, and invoke compression]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def start(self):
        src = self.input_dir.get().strip()
        dst = self.output_dir.get().strip()
        seven_zip_path = self.seven_zip.get().strip()
        split_size_val = self.split_size.get().strip()
        max_cpu = self.max_cpu_percent.get()
        priority = self.priority_mode.get().strip()

        if not src or not dst:
            self.logbox.log("エラー: 入力・出力フォルダを指定してください")
            return
        if not os.path.isdir(src):
            self.logbox.log(f"エラー: 入力フォルダが存在しません: {src}")
            return
        if not os.path.isfile(seven_zip_path):
            self.logbox.log(f"エラー: 7-Zip が存在しません: {seven_zip_path}")
            return
        try:
            os.makedirs(dst, exist_ok=True)
        except Exception as e:
            self.logbox.log(f"エラー: 出力フォルダを作成できません: {e}")
            return

        self.compress_files(src, dst, seven_zip_path, split_size_val, max_cpu, priority)
        self.logbox.log("圧縮処理が終了しました")

    # {
    #   責務: [compress_files: input directory直下のfilesをindividual 7z archivesへ圧縮する]
    #   処理: [skip valid existing archives, sanitize names, apply split/CPU/priority settings, stream 7-Zip output, and report status]
    #   引数: [input_dir, output_dir, seven_zip, split_size, max_cpu_percent, priority_mode]
    #   戻り値: [処理結果]
    # }
    def compress_files(
        self, input_dir, output_dir, seven_zip, split_size, max_cpu_percent, priority_mode
    ):
        os.makedirs(output_dir, exist_ok=True)
        for filename in os.listdir(input_dir):
            file_path = os.path.join(input_dir, filename)
            if not os.path.isfile(file_path):
                continue
            base_name = os.path.splitext(filename)[0]
            safe_base_name = self.sanitize_filename(base_name)
            zip_path = os.path.join(output_dir, safe_base_name + ".7z")

            if os.path.exists(zip_path):
                zip_size = os.path.getsize(zip_path)
                if zip_size > 1024:
                    self.logbox.log(f"⏩ スキップ: 既に存在する圧縮ファイル: {zip_path}")
                    continue
                else:
                    self.logbox.log(f"⚠️ 小さすぎるファイルを検出: 上書きします: {zip_path}")

            file_size = os.path.getsize(file_path)
            options = ["-mx=3"]
            if isinstance(max_cpu_percent, int) and 1 <= max_cpu_percent <= 100:
                threads = self.compute_threads_from_percent(max_cpu_percent)
                options.insert(0, f"-mmt={threads}")
                self.logbox.log(
                    f"💡 max CPU {max_cpu_percent}% を設定: 7z に -mmt={threads} を指定します"
                )

            if file_size > 3 * 1024 * 1024 * 1024:
                options.append("-v" + split_size)

            cmd = [seven_zip, "a"] + options + [zip_path, file_path]

            creationflags = 0
            if os.name == "nt":
                mode = (priority_mode or "below_normal").lower()
                if mode == "idle":
                    creationflags = 0x00000040
                elif mode == "normal":
                    creationflags = 0
                else:
                    creationflags = 0x00004000

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )

            if isinstance(max_cpu_percent, int) and 1 <= max_cpu_percent <= 100 and _HAS_PSUTIL:
                cpu_count = os.cpu_count() or 1
                allowed = max(1, round(cpu_count * max_cpu_percent / 100.0))
                cores = list(range(allowed))
                self.set_affinity_for_pid(proc.pid, cores)
                self.logbox.log(
                    f"🔧 プロセスPID {proc.pid} のCPUアフィニティを {cores} に設定しました"
                )
            elif (
                isinstance(max_cpu_percent, int) and 1 <= max_cpu_percent <= 100 and not _HAS_PSUTIL
            ):
                self.logbox.log(
                    "⚠️ psutil が見つかりません。-mmt によるスレッド制限のみ行います。psutil を入れるとプロセスアフィニティも設定できます。"
                )

            for line in proc.stdout or ():
                line = line.rstrip()
                if line:
                    self.logbox.log(line)
            return_code = proc.wait()
            if return_code == 0:
                self.logbox.log(f"✅ 圧縮成功: {filename} -> {zip_path}")
            else:
                self.logbox.log(f"❌ 圧縮失敗: {filename} (code={return_code})")

    # {
    #   責務: [compute_threads_from_percent: CPU percentageから7-Zip thread countを計算する]
    #   処理: [scale available logical CPU count and clamp to at least one]
    #   引数: [percent]
    #   戻り値: [処理結果]
    # }
    @staticmethod
    def compute_threads_from_percent(percent):
        cpu_count = os.cpu_count() or 1
        threads = max(1, round(cpu_count * percent / 100.0))
        return threads

    # {
    #   責務: [sanitize_filename: archive basenameをWindows-safeなfilenameへ変換する]
    #   処理: [replace forbidden control/path characters and emoji with underscores]
    #   引数: [name]
    #   戻り値: [処理結果]
    # }
    @staticmethod
    def sanitize_filename(name):
        # Windows 対応: 禁止文字をアンダースコアに置換
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        # 絵文字をアンダースコアに置換
        emoji_pattern = re.compile(
            "[\U0001f300-\U0001f5ff"
            "\U0001f600-\U0001f64f"
            "\U0001f680-\U0001f6ff"
            "\U0001f700-\U0001f77f"
            "\U0001f780-\U0001f7ff"
            "\U0001f800-\U0001f8ff"
            "\U0001f900-\U0001f9ff"
            "\U0001fa00-\U0001fa6f"
            "\U0001fa70-\U0001faff"
            "\u2600-\u26ff"
            "\u2700-\u27bf]+"
        )
        name = emoji_pattern.sub("_", name)
        return name or "_"

    # {
    #   責務: [set_affinity_for_pid: 7-Zip processへallowed CPU affinityを適用する]
    #   処理: [set psutil affinity and print failure without stopping compression]
    #   引数: [pid, allowed_cores]
    #   戻り値: [処理結果]
    # }
    @staticmethod
    def set_affinity_for_pid(pid, allowed_cores):
        try:
            p = psutil.Process(pid)
            p.cpu_affinity(allowed_cores)
        except Exception as e:
            print(f"⚠️  CPUアフィニティの設定に失敗しました: {e}")
