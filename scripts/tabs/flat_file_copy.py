from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

class FlatFileCopyTab(ttk.Frame):
    DEFAULT_OPERATION = "move"
    DEFAULT_INPUT_DIR = USER_PATHS["flat_copy_input_dir"]
    DEFAULT_OUTPUT_DIR = USER_PATHS["flat_copy_output_dir"]

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.operation = tk.StringVar(value=self.DEFAULT_OPERATION)
        self.preset_store = PresetStore("flat_file_copy")
        self.preset_name = tk.StringVar()
        self.input_dir = tk.StringVar(value=self.DEFAULT_INPUT_DIR)
        self.output_dir = tk.StringVar(value=self.DEFAULT_OUTPUT_DIR)
        self._build()

    def _build(self):
        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="操作", width=22).pack(side="left")
        ttk.Radiobutton(row, text="コピー", variable=self.operation, value="copy").pack(side="left")
        ttk.Radiobutton(row, text="移動", variable=self.operation, value="move").pack(side="left", padx=(10, 0))

        LabeledPathRow(self, "input_dir", self.input_dir, mode="dir").pack(fill="x", pady=4)
        LabeledPathRow(self, "output_dir", self.output_dir, mode="dir").pack(fill="x", pady=4)
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="実行", command=self.run_thread).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16,4)); self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left"); ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4); ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"operation": self.operation.get(), "input_dir": self.input_dir.get(), "output_dir": self.output_dir.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get()); self.operation.set(values.get("operation", self.operation.get())); self.input_dir.set(values.get("input_dir", self.input_dir.get())); self.output_dir.set(values.get("output_dir", self.output_dir.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    def run_thread(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        operation = self.operation.get().strip()
        input_dir = self.input_dir.get().strip()
        output_dir = self.output_dir.get().strip()
        if operation not in ("copy", "move"):
            self.logbox.log("エラー: 操作は copy または move を指定してください")
            return
        if not os.path.isdir(input_dir):
            self.logbox.log(f"エラー: input_dir が存在しません: {input_dir}")
            return
        os.makedirs(output_dir, exist_ok=True)

        self.logbox.log(f"開始: {operation} / {input_dir} -> {output_dir}")
        used_names = set(os.listdir(output_dir))
        name_counters: dict[str, int] = {}
        processed = 0
        skipped = 0

        for root, _dirs, files in os.walk(input_dir):
            for file in files:
                src_path = os.path.join(root, file)
                dst_name = file
                dst_path = os.path.join(output_dir, dst_name)

                if os.path.exists(dst_path):
                    try:
                        same_file = os.path.samefile(src_path, dst_path)
                    except FileNotFoundError:
                        same_file = False

                    if same_file:
                        if operation == "move":
                            skipped += 1
                            continue
                        dst_name = None
                    else:
                        base, ext = os.path.splitext(file)
                        i = name_counters.get(file, 1)
                        while True:
                            candidate_name = f"{base}_{i}{ext}"
                            candidate_path = os.path.join(output_dir, candidate_name)
                            if candidate_name not in used_names and not os.path.exists(candidate_path):
                                dst_name = candidate_name
                                dst_path = candidate_path
                                name_counters[file] = i + 1
                                break
                            i += 1

                if dst_name is None:
                    skipped += 1
                    continue

                try:
                    used_names.add(dst_name)
                    if operation == "copy":
                        shutil.copy2(src_path, dst_path)
                    else:
                        shutil.move(src_path, dst_path)
                    processed += 1
                except Exception as e:
                    self.logbox.log(f"エラー: {src_path} -> {dst_path}: {e}")

        verb = "コピー" if operation == "copy" else "移動"
        self.logbox.log(f"完了: {processed}件を{verb}しました / スキップ {skipped}件")
