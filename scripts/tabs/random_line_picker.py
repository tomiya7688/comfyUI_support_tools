from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

class RandomLinePickerTab(ttk.Frame):
    """random_line_picker.py を統合版に内包したタブ。

    ターミナルには出さず、このタブのログ欄だけに進捗を表示します。
    元スクリプトの初期値は維持しています。
    """
    DEFAULT_INPUT_FILE = str(WILDCARDS_DIR / "1girl_bestquality.txt")
    DEFAULT_OUTPUT_FILE = str(A1111_DIR / "outputs" / "text" / "1girl_bestquality_output4.txt")
    DEFAULT_LOOPS = "100000"
    MAX_DEPTH = 20

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.preset_store = PresetStore("random_line_picker")
        self.preset_name = tk.StringVar()

        self.input_file = tk.StringVar(value=self.DEFAULT_INPUT_FILE)
        self.output_file = tk.StringVar(value=self.DEFAULT_OUTPUT_FILE)
        self.loops = tk.StringVar(value=self.DEFAULT_LOOPS)
        self.root_dir = tk.StringVar(value=os.path.dirname(self.DEFAULT_INPUT_FILE))
        self.auto_root_dir = tk.BooleanVar(value=True)
        self.show_each_line = tk.BooleanVar(value=True)

        self._build()

    def _build(self):
        top = ttk.LabelFrame(self, text="Random Line Picker", padding=8)
        top.pack(fill="x")

        LabeledPathRow(
            top,
            "input_file",
            self.input_file,
            mode="file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        ).pack(fill="x", pady=3)

        LabeledPathRow(
            top,
            "output_file / dir",
            self.output_file,
            mode="save",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        ).pack(fill="x", pady=3)

        row = ttk.Frame(top)
        row.pack(fill="x", pady=3)
        ttk.Label(row, text="loops", width=22).pack(side="left", padx=(0, 6))
        ttk.Entry(row, textvariable=self.loops, width=12).pack(side="left")
        ttk.Checkbutton(row, text="各行をログ表示", variable=self.show_each_line).pack(side="left", padx=(16, 0))

        root_row = ttk.Frame(top)
        root_row.pack(fill="x", pady=3)
        ttk.Label(root_row, text="root_dir", width=22).pack(side="left", padx=(0, 6))
        ttk.Entry(root_row, textvariable=self.root_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(root_row, text="参照", command=self.select_root_dir).pack(side="left", padx=(6, 0))

        ttk.Checkbutton(
            top,
            text="input_file のフォルダを root_dir に自動反映",
            variable=self.auto_root_dir,
        ).pack(anchor="w", pady=(2, 0))

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="生成開始", command=self.start).pack(side="left", padx=4)
        ttk.Button(buttons, text="停止", command=self.stop).pack(side="left", padx=4)
        ttk.Button(buttons, text="ログ消去", command=self.clear_log).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)

        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self.logbox.log("Random Line Picker タブを起動しました")
        self.logbox.log(f"input_file 初期値: {self.DEFAULT_INPUT_FILE}")
        self.logbox.log(f"output_file 初期値: {self.DEFAULT_OUTPUT_FILE}")
        self.logbox.log(f"loops 初期値: {self.DEFAULT_LOOPS}")
        self._refresh_preset_choices()

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            values = {
                "input_file": self.input_file.get(),
                "output_file": self.output_file.get(),
                "loops": self.loops.get(),
                "root_dir": self.root_dir.get(),
                "auto_root_dir": self.auto_root_dir.get(),
                "show_each_line": self.show_each_line.get(),
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
            self.input_file.set(values.get("input_file", self.input_file.get()))
            self.output_file.set(values.get("output_file", self.output_file.get()))
            self.loops.set(str(values.get("loops", self.loops.get())))
            self.root_dir.set(values.get("root_dir", self.root_dir.get()))
            self.auto_root_dir.set(bool(values.get("auto_root_dir", self.auto_root_dir.get())))
            self.show_each_line.set(bool(values.get("show_each_line", self.show_each_line.get())))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    def select_root_dir(self):
        path = filedialog.askdirectory(initialdir=self.root_dir.get().strip() or os.getcwd())
        if path:
            self.root_dir.set(path)

    def clear_log(self):
        self.logbox.delete("1.0", "end")

    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.logbox.log("すでに実行中です。停止してから再実行してください。")
            return
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self.run_safe, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.stop_event.set()
        self.logbox.log("停止要求を送信しました")

    def run_safe(self):
        try:
            self.run()
        except Exception as e:
            import traceback
            self.logbox.log("❌ Random Line Picker エラー:")
            self.logbox.log("".join(traceback.format_exception_only(type(e), e)).strip())

    def _resolve_output_path(self, output_path: str) -> str:
        output_path = output_path.strip()
        if not output_path:
            raise ValueError("output_file が空です")

        # ディレクトリのみ、または拡張子なしなら日時ファイル名を作る
        if os.path.isdir(output_path) or not os.path.splitext(output_path)[1]:
            os.makedirs(output_path, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return os.path.join(output_path, f"output_{timestamp}.txt")

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        return output_path

    @staticmethod
    def _expand_choices(text: str) -> str:
        pattern = re.compile(r"\{([^{}]+)\}")
        while True:
            match = pattern.search(text)
            if not match:
                break
            options = [part.strip() for part in match.group(1).split("|")]
            choice = secrets.choice(options) if options else ""
            text = text[:match.start()] + choice + text[match.end():]
        return text

    def process_file(self, rel_path: str, root_dir: str, parent: str | None = None, depth: int = 0) -> str:
        if self.stop_event.is_set():
            return ""
        if depth > self.MAX_DEPTH:
            raise RecursionError(f"ワイルドカードのネストが深すぎます: {rel_path}")

        filepath = os.path.join(root_dir, rel_path)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            ref_from = parent if parent else "(top-level)"
            raise FileNotFoundError(f"No such file or directory: '{filepath}' (referenced in '{ref_from}')")

        if not lines:
            return ""

        chosen_line = secrets.choice(lines)
        chosen_line = self._expand_choices(chosen_line)

        def repl(match):
            key = match.group(1)
            nested_rel = f"{key}.txt"
            return self.process_file(nested_rel, root_dir, parent=rel_path, depth=depth + 1)

        result = re.sub(r"__(.*?)__", repl, chosen_line)
        return self._expand_choices(result)

    def run(self):
        input_file = self.input_file.get().strip()
        output_file = self.output_file.get().strip()

        if not input_file:
            self.logbox.log("エラー: input_file が空です")
            return
        if not os.path.isfile(input_file):
            self.logbox.log(f"エラー: input_file が存在しません: {input_file}")
            return

        try:
            loops = int(self.loops.get().strip())
            if loops <= 0:
                raise ValueError
        except ValueError:
            self.logbox.log("エラー: loops は正の整数で指定してください")
            return

        if self.auto_root_dir.get():
            root_dir = os.path.dirname(input_file)
            self.root_dir.set(root_dir)
        else:
            root_dir = self.root_dir.get().strip() or os.path.dirname(input_file)

        output_path = self._resolve_output_path(output_file)
        base_name = os.path.basename(input_file)

        self.logbox.log("処理開始")
        self.logbox.log(f"input_file: {input_file}")
        self.logbox.log(f"root_dir: {root_dir}")
        self.logbox.log(f"output_path: {output_path}")
        self.logbox.log(f"loops: {loops}")

        # 元スクリプトと同じく、開始時に出力ファイルを初期化
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("")

        generated = 0
        with open(output_path, "a", encoding="utf-8") as f_out:
            for i in range(loops):
                if self.stop_event.is_set():
                    self.logbox.log(f"停止しました: {generated}/{loops} 行生成済み")
                    break
                try:
                    result = self.process_file(base_name, root_dir)
                except FileNotFoundError as e:
                    self.logbox.log(f"FileNotFoundError: {e}")
                    break
                except Exception as e:
                    self.logbox.log(f"❌ Iteration {i+1}/{loops} でエラー: {type(e).__name__}: {e}")
                    break

                f_out.write(result + "\n")
                generated += 1
                if self.show_each_line.get():
                    self.logbox.log(f"Iteration {i+1}/{loops}: {result}")
                elif generated == 1 or generated % 100 == 0:
                    self.logbox.log(f"進捗: {generated}/{loops}")

        self.logbox.log(f"Output saved to: {output_path}")
        self.logbox.log(f"生成行数: {generated}")
