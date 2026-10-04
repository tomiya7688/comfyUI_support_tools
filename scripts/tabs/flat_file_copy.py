from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

# {
#   "責務": "入力ツリー内のファイルを1フォルダへ平坦化してコピーまたは移動するUI。",
#   "フィールド": ["DEFAULT_OPERATION: 初期操作種別", "DEFAULT_INPUT_DIR: 初期入力フォルダ", "DEFAULT_OUTPUT_DIR: 初期出力フォルダ", "operation: copy/move選択", "preset_store: 設定保存先", "preset_name: 選択プリセット", "input_dir: 入力フォルダ", "output_dir: 出力フォルダ", "logbox: 実行ログ"]
# }
class FlatFileCopyTab(ttk.Frame):
    DEFAULT_OPERATION = "move"
    DEFAULT_INPUT_DIR = USER_PATHS["flat_copy_input_dir"]
    DEFAULT_OUTPUT_DIR = USER_PATHS["flat_copy_output_dir"]

    # {
    #   "責務": "操作・入出力フォルダを初期化して画面を作る。",
    #   "処理": ["初期設定とプリセット保存先を用意する", "操作選択・パス欄・操作ボタン・ログ領域を構築する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.operation = tk.StringVar(value=self.DEFAULT_OPERATION)
        self.preset_store = PresetStore("flat_file_copy")
        self.preset_name = tk.StringVar()
        self.input_dir = tk.StringVar(value=self.DEFAULT_INPUT_DIR)
        self.output_dir = tk.StringVar(value=self.DEFAULT_OUTPUT_DIR)
        self._build()

    # {
    #   "責務": "ファイル操作に必要な入力・操作・ログUIを配置する。",
    #   "処理": ["copy/move選択と入出力path欄を配置する", "開始・プリセット操作とログ領域を配置する"],
    #   "引数": [],
    #   "戻り値": []
    # }
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

    # {
    #   "責務": "プリセット名を選択UIへ反映する。",
    #   "処理": ["PresetStoreの名前一覧でcomboboxを更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "操作種別と入出力フォルダをプリセットとして保存する。",
    #   "処理": ["現在の設定を保存し名前・選択肢を更新する", "成否をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"operation": self.operation.get(), "input_dir": self.input_dir.get(), "output_dir": self.output_dir.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択したプリセットから操作種別と入出力フォルダを復元する。",
    #   "処理": ["保存値を各入力状態へ反映する", "成否をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get()); self.operation.set(values.get("operation", self.operation.get())); self.input_dir.set(values.get("input_dir", self.input_dir.get())); self.output_dir.set(values.get("output_dir", self.output_dir.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "ファイルコピーまたは移動処理をdaemon threadで開始する。",
    #   "処理": ["runをworker threadで起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run_thread(self):
        threading.Thread(target=self.run, daemon=True).start()

    # {
    #   "責務": "入力フォルダ配下の各ファイルを出力直下へコピーまたは移動する。",
    #   "処理": ["設定と入力folderを検証する", "出力名の衝突を回避しながら全階層を走査する", "処理・skip件数をログへ報告する"],
    #   "引数": [],
    #   "戻り値": []
    # }
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
