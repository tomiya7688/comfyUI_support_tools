from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore

# {
#   "責務": "禁止tag listに一致するtagをprompt txt群から除いて上書きするUI。",
#   "フィールド": ["DEFAULT_DELETE_TAG: 初期禁止tag file", "delete_tag_path: 禁止tag入力", "prompt_target_path: 対象file/folder", "preset_store/preset_name/preset_combo: 設定管理", "logbox: 処理結果表示"]
# }
class TagDeleterTab(ttk.Frame):
    DEFAULT_DELETE_TAG = str(INPUT_MODELS_DIR / "tag_deleter" / "tagger_ng_tags_for_character.txt")

    # {
    #   "責務": "禁止tagとprompt対象pathを初期化し画面を構築する。",
    #   "処理": ["初期tag fileとpreset storeを設定する", "tag/input選択・実行・log widgetを作る"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.delete_tag_path = tk.StringVar(value=self.DEFAULT_DELETE_TAG)
        self.prompt_target_path = tk.StringVar(value="")
        self.preset_store = PresetStore("tag_deleter")
        self.preset_name = tk.StringVar()
        self._build()

    # {
    #   "責務": "禁止tag fileとprompt file/folderの選択・実行UIを配置する。",
    #   "処理": ["path entryとfile/folder dialog buttonを設置する", "preset操作とlog領域を追加する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        LabeledPathRow(self, "delete_tag_input", self.delete_tag_path, mode="file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=4)

        frame = ttk.Frame(self)
        frame.pack(fill="x", pady=4)
        ttk.Label(frame, text="prompt_file_input / dir", width=22).pack(side="left", padx=(0, 6))
        ttk.Entry(frame, textvariable=self.prompt_target_path).pack(side="left", fill="x", expand=True)
        ttk.Button(frame, text="ファイル参照", command=self.select_prompt_file).pack(side="left", padx=(6, 0))
        ttk.Button(frame, text="フォルダ参照", command=self.select_prompt_dir).pack(side="left", padx=(6, 0))

        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="実行", command=self.run_thread).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16,4)); self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left"); ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4); ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self.logbox.log(f"delete_tag_input 初期値: {self.DEFAULT_DELETE_TAG}")
        self._refresh_preset_choices()

    # {
    #   "責務": "保存済みpreset名をcomboboxへ設定する。",
    #   "処理": ["PresetStoreから名前一覧を取得して反映する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "禁止tag fileとprompt対象pathをpresetへ保存する。",
    #   "処理": ["現在のpathを保存する", "名前・一覧・成否logを更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"delete_tag_path": self.delete_tag_path.get(), "prompt_target_path": self.prompt_target_path.get()}); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択presetから禁止tagとprompt対象pathを復元する。",
    #   "処理": ["保存pathを対応variableへ設定する", "結果をlogへ報告する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get()); self.delete_tag_path.set(values.get("delete_tag_path", self.delete_tag_path.get())); self.prompt_target_path.set(values.get("prompt_target_path", self.prompt_target_path.get())); self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "処理対象prompt txtを選択dialogから指定する。",
    #   "処理": ["txt選択dialogを表示する", "path選択時prompt_target_pathへ設定する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def select_prompt_file(self):
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if path:
            self.prompt_target_path.set(path)

    # {
    #   "責務": "処理対象prompt folderを選択dialogから指定する。",
    #   "処理": ["folder選択dialogを表示する", "path選択時prompt_target_pathへ設定する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def select_prompt_dir(self):
        path = filedialog.askdirectory()
        if path:
            self.prompt_target_path.set(path)

    # {
    #   "責務": "file処理をdaemon threadで起動する。",
    #   "処理": ["process_filesをworker threadで実行する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run_thread(self):
        threading.Thread(target=self.process_files, daemon=True).start()

    # {
    #   "責務": "tagのcaseと空白・underscore差を無視する比較keyを作る。",
    #   "処理": ["strip/casefoldし連続whitespaceとunderscoreをspaceへ統一する"],
    #   "引数": {"tag": "正規化するtag"},
    #   "戻り値": "比較用の正規化tag"
    # }
    @staticmethod
    def normalize_tag(tag: str) -> str:
        return re.sub(r"[\s_]+", " ", tag.strip().casefold())

    # {
    #   "責務": "wildcard・LoRA等の特殊prompt tokenを保護対象と判定する。",
    #   "処理": ["token全体をwildcardまたは対応extension構文に照合する"],
    #   "引数": {"tag": "判定するcomma区切りtoken"},
    #   "戻り値": "特殊構文ならTrue、それ以外False"
    # }
    @staticmethod
    def is_protected_prompt_token(tag: str) -> bool:
        token = tag.strip()
        return bool(re.fullmatch(r"__.+__", token) or re.fullmatch(r"<\s*(?:lora|lyco|hypernet|embedding)\s*:[^>]+>", token, re.IGNORECASE))

    # {
    #   "責務": "禁止tag fileを読み正規化済みtag集合を構築する。",
    #   "処理": ["行単位に空行と末尾commaを処理する", "比較用tag keyをsetへ追加する"],
    #   "引数": {"file_path": "禁止tagを1行1件で記載したfile path"},
    #   "戻り値": "正規化済み禁止tagのset"
    # }
    @staticmethod
    def load_delete_tags(file_path: str) -> set[str]:
        tags: set[str] = set()
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                tag = line.strip()
                if not tag:
                    continue
                if tag.endswith(","):
                    tag = tag[:-1].strip()
                if tag:
                    tags.add(TagDeleterTab.normalize_tag(tag))
        return tags

    # {
    #   "責務": "1行のcomma区切りtagから禁止tagを除き改行状態を保って返す。",
    #   "処理": ["空行と末尾改行を識別する", "保護tokenまたは禁止tag membershipに従いfilterする", "残ったtokenをcommaで結合する"],
    #   "引数": {"line": "入力prompt line", "delete_tags": "正規化済み禁止tag set"},
    #   "戻り値": "禁止tag除去後のline"
    # }
    @staticmethod
    def clean_prompt_line(line: str, delete_tags: set[str]) -> str:
        has_newline = line.endswith("\n")
        stripped_line = line.rstrip("\n").strip()
        if not stripped_line:
            return "\n" if has_newline else ""
        parts = [p.strip() for p in stripped_line.split(",")]
        filtered_parts = [
            part for part in parts
            if part and (TagDeleterTab.is_protected_prompt_token(part) or TagDeleterTab.normalize_tag(part) not in delete_tags)
        ]
        new_line = ",".join(filtered_parts)
        if has_newline:
            new_line += "\n"
        return new_line

    # {
    #   "責務": "選択pathから処理可能なtxt file一覧を得る。",
    #   "処理": ["単一fileならtxt拡張子を確認する", "folderなら直下txtをcase-insensitive順に並べる", "その他pathは空listを返す"],
    #   "引数": {"target_path": "対象fileまたはfolder path"},
    #   "戻り値": "対象txtのPath list"
    # }
    @staticmethod
    def get_target_txt_files(target_path: str) -> list[Path]:
        path = Path(target_path)
        if path.is_file():
            return [path] if path.suffix.lower() == ".txt" else []
        if path.is_dir():
            return sorted([p for p in path.iterdir() if p.is_file() and p.suffix.lower() == ".txt"])
        return []

    # {
    #   "責務": "禁止tagを読み対象txt全体から削除して各fileを上書きする。",
    #   "処理": ["入力pathを検査する", "禁止tag setと対象file listを作る", "各行をcleanして上書きし変更件数を集計する", "結果または例外をlogへ報告する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def process_files(self):
        delete_tag_file = self.delete_tag_path.get().strip()
        prompt_target = self.prompt_target_path.get().strip()
        if not delete_tag_file:
            self.logbox.log("エラー: delete_tag_input が未指定です")
            return
        if not prompt_target:
            self.logbox.log("エラー: prompt_file_input またはディレクトリが未指定です")
            return
        try:
            self.logbox.log("処理開始")
            self.logbox.log(f"delete_tag_input: {delete_tag_file}")
            self.logbox.log(f"処理対象: {prompt_target}")
            delete_tags = self.load_delete_tags(delete_tag_file)
            self.logbox.log(f"削除対象タグ数: {len(delete_tags)}")
            target_files = self.get_target_txt_files(prompt_target)
            if not target_files:
                self.logbox.log("エラー: 処理対象の .txt ファイルが見つかりませんでした")
                return

            total_changed = 0
            total_lines = 0
            for file_path in target_files:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_lines = []
                changed_count = 0
                for line in lines:
                    new_line = self.clean_prompt_line(line, delete_tags)
                    if new_line != line:
                        changed_count += 1
                    new_lines.append(new_line)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                total_changed += changed_count
                total_lines += len(lines)
                self.logbox.log(f"完了: {file_path} / 変更行数: {changed_count} / 総行数: {len(lines)}")

            self.logbox.log("----")
            self.logbox.log("全処理完了")
            self.logbox.log(f"処理ファイル数: {len(target_files)}")
            self.logbox.log(f"合計行数: {total_lines}")
            self.logbox.log(f"合計変更行数: {total_changed}")
            self.logbox.log("すべて上書き保存しました")
        except Exception as e:
            self.logbox.log(f"エラー発生: {e}")
