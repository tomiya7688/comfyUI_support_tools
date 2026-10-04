from __future__ import annotations

import re
from pathlib import Path

from ..context import *
from ..services import *
from ..widgets.preset_store import PresetStore


# {
#   "責務": "タグ列を重複除去しprefix/suffixを加えてpromptへ整形するUI。",
#   "フィールド": ["input_file/output_file: file path", "prefix/suffix: 追加文字列", "preset_store/preset_name/preset_combo: 設定管理", "source/result: 入出力text widget", "logbox: 処理結果表示"]
# }
class TagToPromptTab(ttk.Frame):
    """タグ列を重複のない生成プロンプトへ整形する。"""

    # {
    #   "責務": "tag入力・出力・prefix/suffix・preset stateを初期化する。",
    #   "処理": ["default outputとpreset storeを設定する", "tag入力・整形・出力widgetを構築する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar(value=str(USER_DATA_DIR / "output" / "tag_to_prompt" / "prompt.txt"))
        self.prefix = tk.StringVar()
        self.suffix = tk.StringVar()
        self.preset_store = PresetStore("tag_to_prompt")
        self.preset_name = tk.StringVar()
        self._build()

    # {
    #   "責務": "tag file・prefix/suffix・入力結果・操作UIを配置する。",
    #   "処理": ["入出力path欄とtext areaを作る", "読込・整形・copy・preset操作を結ぶ"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        LabeledPathRow(self, "tagファイル（任意）", self.input_file, mode="file", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=3)
        LabeledPathRow(self, "出力ファイル", self.output_file, mode="save", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=3)
        for label, variable in (("先頭に追加", self.prefix), ("末尾に追加", self.suffix)):
            row = ttk.Frame(self); row.pack(fill="x", pady=3)
            ttk.Label(row, text=label, width=16).pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        source_frame = ttk.LabelFrame(self, text="タグ入力（tagファイルを指定した場合は、その内容をここへ読み込みます）", padding=6)
        source_frame.pack(fill="both", expand=True, pady=(5, 3))
        self.source = ScrolledText(source_frame, height=8, wrap="word")
        self.source.pack(fill="both", expand=True)
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="ファイルを読込", command=self.read_file).pack(side="left")
        ttk.Button(buttons, text="整形・保存", command=self.process).pack(side="left", padx=4)
        ttk.Button(buttons, text="結果をコピー", command=self.copy_result).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        output_frame = ttk.LabelFrame(self, text="生成プロンプト", padding=6)
        output_frame.pack(fill="both", expand=True, pady=3)
        self.result = ScrolledText(output_frame, height=7, wrap="word")
        self.result.pack(fill="both", expand=True)
        self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True, pady=(4, 0))
        self._refresh_preset_choices()

    # {
    #   "責務": "Text widgetの本文を末尾改行なしで取得する。",
    #   "処理": ["先頭からend-1cまでのtextを読む"],
    #   "引数": {"widget": "読み取り元Text widget"},
    #   "戻り値": "Text widget本文"
    # }
    @staticmethod
    def _text(widget):
        return widget.get("1.0", "end-1c")

    # {
    #   "責務": "Text widgetの内容を指定文字列に置き換える。",
    #   "処理": ["既存textを消す", "valueを先頭位置へ挿入する"],
    #   "引数": {"widget": "書き込み先Text widget", "value": "置換後本文"},
    #   "戻り値": []
    # }
    @staticmethod
    def _set_text(widget, value):
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    # {
    #   "責務": "comma/newline区切りtagを正規化比較して重複を除く。",
    #   "処理": ["tokenを分割して空を除く", "case/space/underscoreを統一したkeyで初出順に重複を除去する"],
    #   "引数": {"text": "区切りtag文字列"},
    #   "戻り値": "重複除去後のtag list"
    # }
    @staticmethod
    def normalize_tags(text):
        tokens = [token.strip() for token in re.split(r"[,\n\r]+", text) if token.strip()]
        unique = []
        seen = set()
        for token in tokens:
            key = re.sub(r"\s+", " ", token.replace("_", " ")).casefold()
            if key not in seen:
                seen.add(key)
                unique.append(token)
        return unique

    # {
    #   "責務": "指定tag text fileをsource入力widgetへ読み込む。",
    #   "処理": ["fileの存在と読み取りを確認する", "source widgetとlogを更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def read_file(self):
        path = Path(self.input_file.get().strip())
        if not path.is_file():
            self.logbox.log(f"tagファイルが存在しません: {path}")
            return
        try:
            self._set_text(self.source, path.read_text(encoding="utf-8"))
            self.logbox.log(f"読み込みました: {path}")
        except OSError as error:
            self.logbox.log(f"読込エラー: {error}")

    # {
    #   "責務": "入力tagを整形し画面表示と出力fileへ書き込む。",
    #   "処理": ["tagの重複を除きprefix/suffixを加える", "result widgetを更新する", "出力pathを作成・保存し件数をlogへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def process(self):
        tags = self.normalize_tags(self._text(self.source))
        result = ", ".join(part for part in (self.prefix.get().strip(), ", ".join(tags), self.suffix.get().strip()) if part)
        self._set_text(self.result, result)
        path = Path(self.output_file.get().strip())
        if not path.name:
            self.logbox.log("出力ファイルを指定してください")
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(result + "\n", encoding="utf-8")
            self.logbox.log(f"保存完了: {len(tags)}タグ / {path}")
        except OSError as error:
            self.logbox.log(f"保存エラー: {error}")

    # {
    #   "責務": "生成prompt結果をclipboardへコピーする。",
    #   "処理": ["空結果を検査する", "result本文をclipboardへ格納しlogを出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def copy_result(self):
        value = self._text(self.result)
        if not value:
            self.logbox.log("コピーする結果がありません")
            return
        self.clipboard_clear(); self.clipboard_append(value)
        self.logbox.log("結果をクリップボードへコピーしました")

    # {
    #   "責務": "preset名一覧をcomboboxへ反映する。",
    #   "処理": ["PresetStoreの名前一覧で選択肢を更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "入出力path・prefix/suffix・source文をpresetへ保存する。",
    #   "処理": ["画面設定をmappingにして保存する", "選択名・一覧・結果logを更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            values = {"input_file": self.input_file.get(), "output_file": self.output_file.get(), "prefix": self.prefix.get(), "suffix": self.suffix.get(), "source": self._text(self.source)}
            path = self.preset_store.save(self.preset_name.get(), values)
            self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択presetからtag入力とprompt整形条件を復元する。",
    #   "処理": ["pathとprefix/suffixを復元する", "source本文を置き換え完了をlogへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (("input_file", self.input_file), ("output_file", self.output_file), ("prefix", self.prefix), ("suffix", self.suffix)):
                variable.set(values.get(key, variable.get()))
            self._set_text(self.source, values.get("source", self._text(self.source)))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")
