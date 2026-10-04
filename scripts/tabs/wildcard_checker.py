from __future__ import annotations

import re
import threading
from pathlib import Path

from ..context import *
from ..services import *
from ..widgets.preset_store import PresetStore


# {
#   "責務": "wildcard txt群の参照存在を検査し、確認可能な表記揺れを任意修正するUI。",
#   "フィールド": ["REFERENCE_PATTERN: __reference__検出pattern", "root_dir: wildcard root", "auto_fix: canonical表記で修正するか", "preset_store/preset_name/preset_combo: 設定管理", "logbox: 検査log"]
# }
class WildcardCheckerTab(ttk.Frame):
    """ワイルドカード参照の存在確認と、表記ゆれの安全な修正を行う。"""

    REFERENCE_PATTERN = re.compile(r"__([^\r\n]+?)__")

    # {
    #   "責務": "root・修正option・presetを初期化してchecker画面を構築する。",
    #   "処理": ["rootとauto-fix変数を設定する", "path・option・操作・log widgetを作る"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.root_dir = tk.StringVar(value=str(WILDCARDS_DIR))
        self.auto_fix = tk.BooleanVar(value=False)
        self.preset_store = PresetStore("wildcard_checker")
        self.preset_name = tk.StringVar()
        self._build()

    # {
    #   "責務": "wildcard root・修正option・検査・preset UIを配置する。",
    #   "処理": ["root folderとauto-fix設定を表示する", "検査・preset buttonとlog領域を作る"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        LabeledPathRow(self, "wildcard root", self.root_dir, mode="dir").pack(fill="x", pady=4)
        ttk.Checkbutton(self, text="確認できた表記ゆれ（大小文字・\\ /）を自動修正", variable=self.auto_fix).pack(anchor="w", pady=4)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="参照を検査", command=self.start).pack(side="left")
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    # {
    #   "責務": "保存済みpreset名をcomboboxへ設定する。",
    #   "処理": ["PresetStoreのnamesを読み選択候補を更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "rootと自動修正optionをpresetとして保存する。",
    #   "処理": ["現在設定を保存する", "選択値・一覧・logを更新する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"root_dir": self.root_dir.get(), "auto_fix": self.auto_fix.get()})
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択presetからrootと修正optionを復元する。",
    #   "処理": ["保存値をroot/auto_fixへ反映する", "読込結果をlogへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.root_dir.set(values.get("root_dir", self.root_dir.get()))
            self.auto_fix.set(bool(values.get("auto_fix", self.auto_fix.get())))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "wildcard参照検査をdaemon threadで開始する。",
    #   "処理": ["run処理をworker threadで起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    # {
    #   "責務": "wildcard参照を安全に正規化しlookup用keyを作る。",
    #   "処理": ["slashを統一して前後slashを除く", "empty・LORA_・dot pathを除外しcanonicalとcasefold keyを返す"],
    #   "引数": {"value": "__...__内のwildcard path"},
    #   "戻り値": "canonical値とcasefold keyのtuple。無効値では空tuple"
    # }
    @staticmethod
    def _reference_key(value):
        normalized = value.strip().replace("\\", "/").strip("/")
        if not normalized or normalized.startswith("LORA_"):
            return "", ""
        if any(part in {"", ".", ".."} for part in normalized.split("/")):
            return "", ""
        return normalized, normalized.casefold()

    # {
    #   "責務": "txt fileとその親folderを大小文字無視で引けるindexにする。",
    #   "処理": ["root相対pathとsuffixなしfile名を作る", "各fileと親folderをcasefold keyで登録する"],
    #   "引数": {"root": "wildcard root path", "files": "検査対象txtのPath列"},
    #   "戻り値": "casefold済み相対nameからcanonical nameへのdict"
    # }
    @staticmethod
    def _index(root, files):
        index = {}
        for path in files:
            relative = path.relative_to(root).with_suffix("").as_posix()
            index.setdefault(relative.casefold(), relative)
            for parent in path.relative_to(root).parents:
                if parent == Path("."):
                    continue
                directory = parent.as_posix()
                index.setdefault(directory.casefold(), directory)
        return index

    # {
    #   "責務": "wildcard root配下の参照を検査し欠損と任意修正を報告する。",
    #   "処理": ["rootとtxt一覧を検証する", "各参照をindexへ照会する", "auto-fix時はcanonical表記へ置換し欠損・件数をlogへ記録する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        root = Path(self.root_dir.get().strip()).expanduser()
        if not root.is_dir():
            self.logbox.log(f"wildcard rootが存在しません: {root}")
            return
        files = sorted((path for path in root.rglob("*.txt") if path.is_file()), key=lambda path: path.as_posix().casefold())
        index = self._index(root, files)
        missing = 0
        repaired = 0
        checked = 0
        self.logbox.log(f"検査開始: {len(files)} ファイル / root={root}")
        for path in files:
            try:
                original = path.read_text(encoding="utf-8")
            except OSError as error:
                self.logbox.log(f"読込失敗: {path}: {error}")
                continue
            replacements = []
            for match in self.REFERENCE_PATTERN.finditer(original):
                raw = match.group(1)
                normalized, key = self._reference_key(raw)
                if not key:
                    continue
                checked += 1
                canonical = index.get(key)
                if canonical is None:
                    missing += 1
                    self.logbox.log(f"欠損参照: {path.relative_to(root)} -> __{raw}__")
                    continue
                if self.auto_fix.get() and raw != canonical:
                    replacements.append((match.start(1), match.end(1), canonical))
            if replacements:
                updated = original
                for start, end, canonical in reversed(replacements):
                    updated = updated[:start] + canonical + updated[end:]
                try:
                    path.write_text(updated, encoding="utf-8")
                    repaired += len(replacements)
                    self.logbox.log(f"修正: {path.relative_to(root)} ({len(replacements)}箇所)")
                except OSError as error:
                    self.logbox.log(f"書込失敗: {path}: {error}")
        self.logbox.log(f"検査完了: 参照 {checked} / 欠損 {missing} / 修正 {repaired}")
