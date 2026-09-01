from __future__ import annotations

import re
import threading
from pathlib import Path

from ..context import *
from ..services import *
from ..widgets.preset_store import PresetStore


class WildcardCheckerTab(ttk.Frame):
    """ワイルドカード参照の存在確認と、表記ゆれの安全な修正を行う。"""

    REFERENCE_PATTERN = re.compile(r"__([^\r\n]+?)__")

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.root_dir = tk.StringVar(value=str(WILDCARDS_DIR))
        self.auto_fix = tk.BooleanVar(value=False)
        self.preset_store = PresetStore("wildcard_checker")
        self.preset_name = tk.StringVar()
        self._build()

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

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"root_dir": self.root_dir.get(), "auto_fix": self.auto_fix.get()})
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.root_dir.set(values.get("root_dir", self.root_dir.get()))
            self.auto_fix.set(bool(values.get("auto_fix", self.auto_fix.get())))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    @staticmethod
    def _reference_key(value):
        normalized = value.strip().replace("\\", "/").strip("/")
        if not normalized or normalized.startswith("LORA_"):
            return "", ""
        if any(part in {"", ".", ".."} for part in normalized.split("/")):
            return "", ""
        return normalized, normalized.casefold()

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
