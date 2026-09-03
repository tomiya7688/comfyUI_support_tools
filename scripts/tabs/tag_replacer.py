from __future__ import annotations

import threading
from pathlib import Path

from ..context import *
from ..backend.tag_replacement_engine import TagReplacementEngine
from ..services import LogBox, LabeledPathRow
from ..widgets.preset_store import PresetStore


class TagReplacerTab(ttk.Frame):
    """タグ置換規則をフォルダ内TXTへ適用する画面。"""

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.recursive = tk.BooleanVar(value=True)
        self.overwrite = tk.BooleanVar(value=False)
        self.preset_name = tk.StringVar()
        self.preset_store = PresetStore("tag_replacer")
        self.rule_rows = []
        self._build()

    def _build(self):
        LabeledPathRow(self, "入力タグフォルダ", self.input_dir, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(self, "出力先（上書き時は不要）", self.output_dir, mode="dir").pack(fill="x", pady=3)
        options = ttk.Frame(self); options.pack(fill="x", pady=3)
        ttk.Checkbutton(options, text="サブフォルダも処理", variable=self.recursive).pack(side="left", padx=4)
        ttk.Checkbutton(options, text="元TXTを上書き", variable=self.overwrite).pack(side="left", padx=4)
        rules = ttk.LabelFrame(self, text="置換規則（完全一致）", padding=6); rules.pack(fill="x", pady=5)
        self.rules_frame = ttk.Frame(rules); self.rules_frame.pack(fill="x")
        ttk.Button(rules, text="規則を追加", command=self._add_rule).pack(anchor="w", pady=(4, 0))
        self._add_rule()
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=5)
        ttk.Button(buttons, text="置換開始", command=self.start).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    def _add_rule(self, value=None):
        value = value or {}
        row = ttk.Frame(self.rules_frame); row.pack(fill="x", pady=2)
        source = tk.StringVar(value=value.get("source", "")); replacement = tk.StringVar(value=value.get("replacement", "")); mode = tk.StringVar(value=value.get("mode", "direct"))
        ttk.Label(row, text="元タグ").pack(side="left"); ttk.Entry(row, textvariable=source, width=24).pack(side="left", padx=3)
        ttk.Combobox(row, textvariable=mode, values=["direct", "wildcard"], state="readonly", width=10).pack(side="left", padx=3)
        ttk.Label(row, text="置換先 / wildcard txt").pack(side="left"); ttk.Entry(row, textvariable=replacement).pack(side="left", fill="x", expand=True, padx=3)
        item = {"row": row, "source": source, "mode": mode, "replacement": replacement}
        ttk.Button(row, text="削除", command=lambda: self._remove_rule(item)).pack(side="left")
        self.rule_rows.append(item)

    def _remove_rule(self, item):
        item["row"].destroy(); self.rule_rows.remove(item)
        if not self.rule_rows: self._add_rule()

    def _rules(self):
        return [{key: item[key].get().strip() for key in ("source", "mode", "replacement")} for item in self.rule_rows if item["source"].get().strip() and item["replacement"].get().strip()]

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), {"input_dir": self.input_dir.get(), "output_dir": self.output_dir.get(), "recursive": self.recursive.get(), "overwrite": self.overwrite.get(), "rules": self._rules()})
            self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get()); self.input_dir.set(values.get("input_dir", self.input_dir.get())); self.output_dir.set(values.get("output_dir", self.output_dir.get())); self.recursive.set(values.get("recursive", self.recursive.get())); self.overwrite.set(values.get("overwrite", self.overwrite.get()))
            for item in self.rule_rows: item["row"].destroy()
            self.rule_rows = []
            for rule in values.get("rules", []): self._add_rule(rule)
            if not self.rule_rows: self._add_rule()
            self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        input_root = Path(self.input_dir.get().strip()); output_root = Path(self.output_dir.get().strip()); rules = self._rules()
        if not input_root.is_dir(): self.logbox.log(f"入力タグフォルダがありません: {input_root}"); return
        if not rules: self.logbox.log("置換規則を1件以上入力してください"); return
        if not self.overwrite.get() and not output_root: self.logbox.log("上書きしない場合は出力先を指定してください"); return
        files = input_root.rglob("*.txt") if self.recursive.get() else input_root.glob("*.txt")
        files = sorted((path for path in files if path.is_file()), key=lambda path: path.as_posix().casefold())
        engine = TagReplacementEngine(); changed = 0; wildcard_cache = {}
        for source in files:
            target = source if self.overwrite.get() else output_root / source.relative_to(input_root)
            changed += engine.process_file(source, target, rules, wildcard_cache)
        self.logbox.log(f"完了: {len(files)}ファイル / 変更行 {changed}")
