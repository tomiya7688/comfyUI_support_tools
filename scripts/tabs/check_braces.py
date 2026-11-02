from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore


# {
#   責務: [CheckBracesTab: TXT wildcard brace checker tab and preset controlsを管理する]
#   処理: [construct inputs, preset controls, log output, file validation, and batch run]
#   フィールド: [input_dir, preset_store, preset_name, preset_combo, logbox]
# }
class CheckBracesTab(ttk.Frame):
    DEFAULT_DIR = str(WILDCARDS_DIR / "anime_character")

    # {
    #   責務: [__init__: 入力directoryとpreset UIを初期化する]
    #   処理: [create widgets and load preset names]
    #   引数: [master]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar(value=self.DEFAULT_DIR)
        self.preset_store = PresetStore("check_braces")
        self.preset_name = tk.StringVar()
        LabeledPathRow(self, "input_dir", self.input_dir, mode="dir").pack(fill="x", pady=4)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=8)
        ttk.Button(
            buttons, text="{} バランス確認", command=lambda: _safe_thread(self.logbox, self.run)
        ).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    # {
    #   責務: [_refresh_preset_choices: preset dropdown choicesを更新する]
    #   処理: [read available preset names and configure combobox]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   責務: [save_preset: 現在のinput directoryをpresetへ保存する]
    #   処理: [save settings and refresh UI, logging validation or filesystem errors]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(
                self.preset_name.get(), {"input_dir": self.input_dir.get()}
            )
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   責務: [load_preset: 選択presetからinput directoryを復元する]
    #   処理: [read saved value and log success or failure]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def load_preset(self):
        try:
            self.input_dir.set(
                self.preset_store.load(self.preset_name.get()).get(
                    "input_dir", self.input_dir.get()
                )
            )
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   責務: [check_file: 一つのtext file内のbrace balanceを検証する]
    #   処理: [scan characters in order, report premature closing or nonzero final balance]
    #   引数: [path]
    #   戻り値: [処理結果]
    # }
    def check_file(self, path):
        bal = 0
        with open(path, "r", encoding="utf-8") as f:
            for no, line in enumerate(f, 1):
                for ch in line:
                    if ch == "{":
                        bal += 1
                    elif ch == "}":
                        bal -= 1
                        if bal < 0:
                            self.logbox.log(
                                f"[ERROR] Too many closing braces in {path} at line {no}"
                            )
                            return False
        if bal != 0:
            self.logbox.log(f"[ERROR] Unbalanced braces in {path}: final balance = {bal}")
            return False
        return True

    # {
    #   責務: [run: 選択directory直下のtxt filesをbrace validationする]
    #   処理: [sort matching files, run per-file checks, and log aggregate result]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def run(self):
        import glob

        files = sorted(glob.glob(os.path.join(self.input_dir.get().strip(), "*.txt")))
        if not files:
            self.logbox.log("txtファイルが見つかりません")
            return
        err = any(not self.check_file(f) for f in files)
        self.logbox.log(
            "One or more files have unbalanced or premature braces."
            if err
            else "All files have balanced braces."
        )
