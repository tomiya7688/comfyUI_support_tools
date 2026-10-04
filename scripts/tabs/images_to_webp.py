from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

# {
#   "責務": "指定フォルダ以下のJPEG/PNGをWebPへ変換するUI。",
#   "フィールド": ["DEFAULT_INPUT_DIR: 初期入力フォルダ", "input_dir: 変換対象", "quality: lossy画質", "lossless: lossless設定", "worker_thread: 実行worker", "preset_store: 設定保存先", "preset_name: 選択プリセット", "preset_combo: 選択肢UI", "logbox: 実行ログ"]
# }
class ImagesToWebpTab(ttk.Frame):
    DEFAULT_INPUT_DIR = USER_PATHS["images_to_webp_input_dir"]
    # {
    #   "責務": "変換設定を初期化し画像変換画面を構築する。",
    #   "処理": ["入力先・品質・圧縮modeとworker状態を初期化する", "変換・プリセット・ログUIを配置する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar(value=self.DEFAULT_INPUT_DIR)
        self.quality = tk.StringVar(value="90")
        self.lossless = tk.BooleanVar(value=False)
        self.worker_thread = None
        self.preset_store = PresetStore("images_to_webp")
        self.preset_name = tk.StringVar()
        LabeledPathRow(self, "変換対象フォルダ", self.input_dir, mode="dir").pack(fill="x", pady=4)
        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="QUALITY").pack(side="left")
        ttk.Entry(row, textvariable=self.quality, width=8).pack(side="left", padx=(4, 12))
        ttk.Checkbutton(row, text="ロスレス保存", variable=self.lossless).pack(side="left")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="変換開始", command=self.start).pack(side="left", padx=4)
        ttk.Button(buttons, text="ログ消去", command=self.clear_log).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    # {
    #   "責務": "保存済み変換プリセットを選択UIへ反映する。",
    #   "処理": ["PresetStoreから名前一覧を取得してcomboboxへ設定する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "現在の対象・品質・lossless設定を保存する。",
    #   "処理": ["現在値をプリセットとして保存する", "名前・選択肢を更新して結果をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            values = {"input_dir": self.input_dir.get(), "quality": self.quality.get(), "lossless": self.lossless.get()}
            path = self.preset_store.save(self.preset_name.get(), values)
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択した変換プリセットを画面へ復元する。",
    #   "処理": ["保存値を入力先・品質・losslessへ反映する", "成否をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.input_dir.set(values.get("input_dir", self.input_dir.get()))
            self.quality.set(str(values.get("quality", self.quality.get())))
            self.lossless.set(bool(values.get("lossless", self.lossless.get())))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "実行ログの表示内容を消去する。",
    #   "処理": ["Text widgetの先頭から末尾を削除する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def clear_log(self):
        self.logbox.delete("1.0", "end")

    # {
    #   "責務": "重複実行を防ぎながらWebP変換workerを開始する。",
    #   "処理": ["既存workerの稼働を確認する", "未実行なら開始ログを出してrun_safeをthread起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.logbox.log("すでに変換中です。停止してから再実行してください。")
            return
        self.logbox.log("変換開始")
        self.worker_thread = threading.Thread(target=self.run_safe, daemon=True)
        self.worker_thread.start()

    # {
    #   "責務": "変換処理の例外をログ化するworker入口。",
    #   "処理": ["runを実行する", "例外時は種別とメッセージをログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run_safe(self):
        try:
            self.run()
        except Exception as e:
            import traceback
            self.logbox.log("❌ 画像変換エラー:")
            self.logbox.log("".join(traceback.format_exception_only(type(e), e)).strip())

    # {
    #   "責務": "画像を現在の設定で隣接WebPへ保存し元ファイルを削除する。",
    #   "処理": ["Pillowで画像を開く", "losslessまたはquality指定でwebpを書き出す", "元画像を削除して出力pathを返す"],
    #   "引数": {"path": "変換対象画像のpath"},
    #   "戻り値": "作成したWebPのPath"
    # }
    def _save_webp(self, path: Path) -> Path:
        pillow_image = _load_pillow_image()
        with pillow_image.open(path) as im:
            out_path = path.with_suffix(".webp")
            if self.lossless.get():
                save_kwargs = {"lossless": True, "method": 6}
            else:
                save_kwargs = {"quality": int(self.quality.get()), "method": 6}
            im.save(out_path, format="WEBP", **save_kwargs)
        path.unlink()
        return out_path

    # {
    #   "責務": "入力folder以下の対応画像を順次WebPへ変換する。",
    #   "処理": ["Pillow・folder・画質設定を検証する", "JPEG/PNGを探索し各画像を保存する", "失敗と完了状況をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        try:
            _load_pillow_image()
        except RuntimeError:
            self.logbox.log("Pillow が見つかりません。pip install pillow を実行してください。")
            return
        root = Path(self.input_dir.get().strip())
        if not root.is_dir():
            self.logbox.log(f"ディレクトリがありません: {root}")
            return
        if not self.lossless.get():
            try:
                quality = int(self.quality.get().strip())
                if quality < 1 or quality > 100:
                    raise ValueError
            except ValueError:
                self.logbox.log(f"QUALITY は 1-100 の整数にしてください: {self.quality.get()}")
                return
        self.logbox.log("ファイル探索中...")
        images = (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in [".jpg", ".jpeg", ".png"])
        count = 0
        for img in images:
            count += 1
            try:
                self.logbox.log(f"[{count}] 変換中: {img}")
                out_path = self._save_webp(img)
                self.logbox.log(f"✅ 変換済み: {out_path}")
            except Exception as e:
                self.logbox.log(f"❌ {img}: {e}")
        if count == 0:
            self.logbox.log(f"画像が見つかりません: {root}")
            return
        self.logbox.log("全処理完了")
