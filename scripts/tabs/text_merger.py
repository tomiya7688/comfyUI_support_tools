from ..context import *
from ..context import _safe_thread
from ..services import *
from ..backend.tag_text_merger import TagTextMerger
from ..widgets.preset_store import PresetStore


# {
#   責務: [TextMergerTab: folder TXT filesをtag-merger serviceで結合するtabとpresetsを管理する]
#   処理: [create source/output, deduplication, preset, and log controls]
#   フィールド: [folder, output, deduplicate, preset_store, logbox]
# }
class TextMergerTab(ttk.Frame):
    DEFAULT_FOLDER = USER_PATHS["text_merger_folder"]
    DEFAULT_OUTPUT = str(WILDCARDS_DIR / "many_prompt_by_artist" / "aie-92915941.txt")

    # {
    #   責務: [__init__: merge paths, deduplication, and preset stateを初期化する]
    #   処理: [initialize Tk variables and build controls]
    #   引数: [master]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.folder = tk.StringVar(value=self.DEFAULT_FOLDER)
        self.output = tk.StringVar(value=self.DEFAULT_OUTPUT)
        self.deduplicate = tk.BooleanVar(value=True)
        self.preset_store = PresetStore("text_merger")
        self.preset_name = tk.StringVar()
        self._build()

    # {
    #   責務: [_build: folder/output paths, deduplication toggle, and merge actionsを構築する]
    #   処理: [compose controls and initialize preset list]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _build(self):
        LabeledPathRow(self, "フォルダ", self.folder, mode="dir").pack(fill="x", pady=4)
        LabeledPathRow(
            self,
            "出力ファイル",
            self.output,
            mode="save",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        ).pack(fill="x", pady=4)
        ttk.Checkbutton(
            self, text="重複タグを追加しない（既存の出力ファイルも照合）", variable=self.deduplicate
        ).pack(anchor="w", pady=2)
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

    # {
    #   責務: [_refresh_preset_choices: preset dropdownをavailable namesで更新する]
    #   処理: [configure values from PresetStore]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   責務: [save_preset: folder/output/deduplicate settingsをpresetへ保存する]
    #   処理: [persist values, refresh selector, and report errors]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(
                self.preset_name.get(),
                {
                    "folder": self.folder.get(),
                    "output": self.output.get(),
                    "deduplicate": self.deduplicate.get(),
                },
            )
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   責務: [load_preset: presetからfolder/output/deduplicate settingsを復元する]
    #   処理: [load controls with current values as defaults]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.folder.set(values.get("folder", self.folder.get()))
            self.output.set(values.get("output", self.output.get()))
            self.deduplicate.set(values.get("deduplicate", True))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   責務: [run_thread: merge actionをdaemon workerで開始する]
    #   処理: [spawn merge callback to keep Tk responsive]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def run_thread(self):
        threading.Thread(target=self.merge, daemon=True).start()

    # {
    #   責務: [merge: folder contentsをTagTextMergerで結合してoutput fileへ保存する]
    #   処理: [validate paths, create empty output for missing input folder, delegate merge policy, and log counts/errors]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def merge(self):
        folder_path = self.folder.get().strip()
        output_file = self.output.get().strip()
        if not folder_path or not output_file:
            self.logbox.log("エラー: フォルダと出力ファイルを指定してください")
            return

        if not os.path.isdir(folder_path):
            self.logbox.log(f"警告: フォルダが存在しません: {folder_path}")
            out_dir = os.path.dirname(output_file)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("")
            self.logbox.log(f"空の出力ファイルを作成しました: {output_file}")
            return

        try:
            result = TagTextMerger().merge(folder_path, output_file, self.deduplicate.get())
            self.logbox.log(
                f"結合完了: {output_file} / ファイル {result['files']} / 追加タグ {result['added']} / 重複スキップ {result['skipped']}"
            )
        except Exception as e:
            self.logbox.log(f"エラー: {output_file} に書き込めませんでした。{e}")
