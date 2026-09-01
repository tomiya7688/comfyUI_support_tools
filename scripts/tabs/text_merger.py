from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

class TextMergerTab(ttk.Frame):
    DEFAULT_FOLDER = USER_PATHS["text_merger_folder"]
    DEFAULT_OUTPUT = str(WILDCARDS_DIR / "many_prompt_by_artist" / "aie-92915941.txt")

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.folder = tk.StringVar(value=self.DEFAULT_FOLDER)
        self.output = tk.StringVar(value=self.DEFAULT_OUTPUT)
        self.preset_store = PresetStore("text_merger")
        self.preset_name = tk.StringVar()
        self._build()

    def _build(self):
        LabeledPathRow(self, "フォルダ", self.folder, mode="dir").pack(fill="x", pady=4)
        LabeledPathRow(self, "出力ファイル", self.output, mode="save", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=4)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="マージ実行", command=self.run_thread).pack(side="left")
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
            path = self.preset_store.save(self.preset_name.get(), {"folder": self.folder.get(), "output": self.output.get()})
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.folder.set(values.get("folder", self.folder.get()))
            self.output.set(values.get("output", self.output.get()))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    def run_thread(self):
        threading.Thread(target=self.merge, daemon=True).start()

    def merge(self):
        folder_path = self.folder.get().strip()
        output_file = self.output.get().strip()
        if not folder_path or not output_file:
            self.logbox.log("エラー: フォルダと出力ファイルを指定してください")
            return

        all_texts: list[str] = []
        if not os.path.isdir(folder_path):
            self.logbox.log(f"警告: フォルダが存在しません: {folder_path}")
            out_dir = os.path.dirname(output_file)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("")
            self.logbox.log(f"空の出力ファイルを作成しました: {output_file}")
            return

        for filename in sorted(os.listdir(folder_path)):
            if filename.endswith(".txt"):
                file_path = os.path.join(folder_path, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        all_texts.append(content)
                    self.logbox.log(f"読み込み成功: {file_path}")
                except Exception as e:
                    self.logbox.log(f"エラー: {file_path} を読み込めませんでした。{e}")

        out_dir = os.path.dirname(output_file)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        try:
            mode = "a+" if os.path.exists(output_file) else "w"
            with open(output_file, mode, encoding="utf-8") as f:
                if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                    f.seek(0, 2)
                    f.seek(max(f.tell() - 1, 0), 0)
                    last_char = f.read(1)
                    if last_char != '\n':
                        f.seek(0, 2)
                        f.write('\n')
                f.write("\n".join(all_texts))
            self.logbox.log(f"結合完了: {output_file}")
        except Exception as e:
            self.logbox.log(f"エラー: {output_file} に書き込めませんでした。{e}")
