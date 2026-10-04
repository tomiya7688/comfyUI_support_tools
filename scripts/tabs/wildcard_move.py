from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..context import *
from ..services import LogBox, LabeledPathRow


# {
#   "責務": "wildcard txt移動時にroot配下のprompt参照を書き換えるUI。",
#   "フィールド": ["PATTERN: wildcard参照を検出する正規表現", "root_dir: wildcard root", "source: 移動元", "destination: 移動先", "logbox: 結果表示"]
# }
class WildcardMoveTab(ttk.Frame):
    """参照を保ったままワイルドカードtxtを移動する。"""

    PATTERN = re.compile(r"__([^\r\n]+?)__")

    # {
    #   "責務": "wildcard rootと移動元・先を初期化し画面を構築する。",
    #   "処理": ["各path入力状態を設定する", "パス欄・参照更新付き移動操作・logを配置する"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.root_dir = tk.StringVar(value=str(WILDCARDS_DIR))
        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self._build()

    # {
    #   "責務": "root・移動元・移動先と実行結果を入力・表示するUIを作る。",
    #   "処理": ["path欄と移動buttonを配置する", "log領域を用意する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        LabeledPathRow(self, "wildcard root", self.root_dir, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(self, "移動元txt", self.source, mode="file", filetypes=[("Text", "*.txt")]).pack(fill="x", pady=3)
        ttk.Label(self, text="移動先（rootからの相対パス。拡張子省略可）").pack(anchor="w", pady=(8, 0))
        ttk.Entry(self, textvariable=self.destination).pack(fill="x", pady=3)
        ttk.Button(self, text="参照を書き換えて移動", command=self.move).pack(anchor="w", pady=6)
        self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True)

    # {
    #   "責務": "移動先または参照pathをwildcard root相対pathへ正規化する。",
    #   "処理": ["絶対pathをroot相対へ変換し、root外pathを拒否して拡張子を除く"],
    #   "引数": {"root": "許可するwildcard root", "value": "入力path"}, "戻り値": "拡張子なしroot相対Path"
    # }
    @staticmethod
    # {
    #   "責務": "入力pathをroot相対の拡張子なしpathへ正規化する。",
    #   "処理": ["絶対pathをroot相対へ変換する", "root外参照を拒否してsuffixを除く"],
    #   "引数": {"root": "許可するwildcard root", "value": "利用者が入力したpath"},
    #   "戻り値": "root相対の拡張子なしPath。root外の場合ValueError"
    # }
    def _relative(root, value):
        path = Path(value.strip())
        if path.is_absolute():
            path = path.resolve().relative_to(root.resolve())
        if ".." in path.parts:
            raise ValueError("root外のパスは指定できません")
        return path.with_suffix("")

    # {
    #   "責務": "移動元wildcardを新しい相対名へ置換してfileを移動する。",
    #   "処理": ["rootとsource/targetを検証する", "root内txtの参照を新しいpathへ更新する", "移動先folderを作成してsourceを移動し結果をログへ出す"],
    #   "引数": [],
    #   "戻り値": []
    # }
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
