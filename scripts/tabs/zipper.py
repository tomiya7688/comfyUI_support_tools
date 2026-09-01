from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

class ZipperTab(ttk.Frame):
    DEFAULT_INPUT_DIR = USER_PATHS["zipper_input_dir"]
    DEFAULT_OUTPUT_DIR = USER_PATHS["zipper_output_dir"]
    DEFAULT_SEVEN_ZIP = USER_PATHS["seven_zip_exe"]
    DEFAULT_SPLIT_SIZE = "3G"
    DEFAULT_MAX_CPU_PERCENT = 10
    DEFAULT_PRIORITY_MODE = "below_normal"

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
        ttk.Entry(settings, textvariable=self.split_size, width=10).grid(row=0, column=1, sticky="w", padx=4, pady=3)
        ttk.Label(settings, text="Max CPU %").grid(row=1, column=0, sticky="w", padx=4, pady=3)
        ttk.Entry(settings, textvariable=self.max_cpu_percent, width=10).grid(row=1, column=1, sticky="w", padx=4, pady=3)
        ttk.Label(settings, text="優先度").grid(row=2, column=0, sticky="w", padx=4, pady=3)
        ttk.Combobox(settings, textvariable=self.priority_mode, values=["idle", "below_normal", "normal"], state="readonly").grid(row=2, column=1, sticky="w", padx=4, pady=3)

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

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            values = {
                "input_dir": self.input_dir.get(), "output_dir": self.output_dir.get(), "seven_zip": self.seven_zip.get(),
                "split_size": self.split_size.get(), "max_cpu_percent": self.max_cpu_percent.get(), "priority_mode": self.priority_mode.get(),
            }
            path = self.preset_store.save(self.preset_name.get(), values)
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

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

    def choose_seven_zip(self):
        path = filedialog.askopenfilename(filetypes=[("7z.exe", "7z.exe"), ("All files", "*.*")])
        if path:
            self.seven_zip.set(path)

    def run_thread(self):
        threading.Thread(target=self.start, daemon=True).start()

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

    def compress_files(self, input_dir, output_dir, seven_zip, split_size, max_cpu_percent, priority_mode):
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
                self.logbox.log(f"💡 max CPU {max_cpu_percent}% を設定: 7z に -mmt={threads} を指定します")

            if file_size > 3 * 1024 * 1024 * 1024:
                options.append('-v' + split_size)

            cmd = [seven_zip, 'a'] + options + [zip_path, file_path]

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
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags
            )

            if isinstance(max_cpu_percent, int) and 1 <= max_cpu_percent <= 100 and _HAS_PSUTIL:
                cpu_count = os.cpu_count() or 1
                allowed = max(1, round(cpu_count * max_cpu_percent / 100.0))
                cores = list(range(allowed))
                self.set_affinity_for_pid(proc.pid, cores)
                self.logbox.log(f"🔧 プロセスPID {proc.pid} のCPUアフィニティを {cores} に設定しました")
            elif isinstance(max_cpu_percent, int) and 1 <= max_cpu_percent <= 100 and not _HAS_PSUTIL:
                self.logbox.log("⚠️ psutil が見つかりません。-mmt によるスレッド制限のみ行います。psutil を入れるとプロセスアフィニティも設定できます。")

            stdout, stderr = proc.communicate()
            if proc.returncode == 0:
                self.logbox.log(f"✅ 圧縮成功: {filename} -> {zip_path}")
            else:
                self.logbox.log(f"❌ 圧縮失敗: {filename}\n{stderr}")

    @staticmethod
    def compute_threads_from_percent(percent):
        cpu_count = os.cpu_count() or 1
        threads = max(1, round(cpu_count * percent / 100.0))
        return threads

    @staticmethod
    def sanitize_filename(name):
        # Windows 対応: 禁止文字をアンダースコアに置換
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
        # 絵文字をアンダースコアに置換
        emoji_pattern = re.compile(
            '[\U0001F300-\U0001F5FF'
            '\U0001F600-\U0001F64F'
            '\U0001F680-\U0001F6FF'
            '\U0001F700-\U0001F77F'
            '\U0001F780-\U0001F7FF'
            '\U0001F800-\U0001F8FF'
            '\U0001F900-\U0001F9FF'
            '\U0001FA00-\U0001FA6F'
            '\U0001FA70-\U0001FAFF'
            '\u2600-\u26FF'
            '\u2700-\u27BF]+'
        )
        name = emoji_pattern.sub('_', name)
        return name or '_'

    @staticmethod
    def set_affinity_for_pid(pid, allowed_cores):
        try:
            p = psutil.Process(pid)
            p.cpu_affinity(allowed_cores)
        except Exception as e:
            print(f"⚠️  CPUアフィニティの設定に失敗しました: {e}")
