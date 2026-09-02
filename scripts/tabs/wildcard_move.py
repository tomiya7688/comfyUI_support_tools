from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..context import *
from ..services import LogBox, LabeledPathRow


class WildcardMoveTab(ttk.Frame):
    """参照を保ったままワイルドカードtxtを移動する。"""

    PATTERN = re.compile(r"__([^\r\n]+?)__")

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.root_dir = tk.StringVar(value=str(WILDCARDS_DIR))
        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self._build()

    def _build(self):
        LabeledPathRow(self, "wildcard root", self.root_dir, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(self, "移動元txt", self.source, mode="file", filetypes=[("Text", "*.txt")]).pack(fill="x", pady=3)
        ttk.Label(self, text="移動先（rootからの相対パス。拡張子省略可）").pack(anchor="w", pady=(8, 0))
        ttk.Entry(self, textvariable=self.destination).pack(fill="x", pady=3)
        ttk.Button(self, text="参照を書き換えて移動", command=self.move).pack(anchor="w", pady=6)
        self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True)

    @staticmethod
    def _relative(root, value):
        path = Path(value.strip())
        if path.is_absolute():
            path = path.resolve().relative_to(root.resolve())
        if ".." in path.parts:
            raise ValueError("root外のパスは指定できません")
        return path.with_suffix("")

    def move(self):
        try:
            root = Path(self.root_dir.get().strip())
            source_rel = self._relative(root, self.source.get())
            target_rel = self._relative(root, self.destination.get())
            source, target = root / source_rel.with_suffix(".txt"), root / target_rel.with_suffix(".txt")
            if not root.is_dir() or not source.is_file(): raise ValueError("rootまたは移動元txtがありません")
            if target.exists(): raise ValueError("移動先が既に存在します")
            old, new = source_rel.as_posix(), target_rel.as_posix()
            changed = 0
            for path in root.rglob("*.txt"):
                text = path.read_text(encoding="utf-8")
                updated = self.PATTERN.sub(lambda m: f"__{new}__" if m.group(1).strip().replace("\\", "/").strip("/") == old else m.group(0), text)
                if updated != text:
                    path.write_text(updated, encoding="utf-8"); changed += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            self.logbox.log(f"移動完了: {old} -> {new} / 参照更新 {changed}ファイル")
        except Exception as error:
            self.logbox.log(f"移動エラー: {error}")
