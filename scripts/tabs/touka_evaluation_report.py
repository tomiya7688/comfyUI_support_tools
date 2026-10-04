from __future__ import annotations

import threading

from ..context import *
from ..backend.touka_evaluation_report import ToukaEvaluationReport
from ..services import LogBox, LabeledPathRow


# {
#   "責務": "Toukaの評価履歴をprofile/presetごとに集計表示しMarkdownへ出力する。",
#   "フィールド": ["history_dir: 評価履歴folder", "output: Markdown出力path", "table: 集計表示widget", "logbox: 実行結果表示"]
# }
class ToukaEvaluationReportTab(ttk.Frame):
    """Display and export grouped Touka evaluation history."""

    # {
    #   "責務": "履歴入力先と出力先を初期化してレポート画面を構築する。",
    #   "処理": ["path変数を初期化する", "入力欄・集計button・table・log領域を作る"],
    #   "引数": {"master": "親Tk widget"},
    #   "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10); self.history_dir = tk.StringVar(); self.output = tk.StringVar(); self._build()

    # {
    #   "責務": "履歴path入力、集計操作、数値table、log領域を配置する。",
    #   "処理": ["folderとMarkdown出力欄を配置する", "評価指標の列を持つtableとログを構築する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def _build(self):
        LabeledPathRow(self, "評価履歴フォルダ", self.history_dir, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(self, "Markdown出力", self.output, mode="save", filetypes=[("Markdown", "*.md"), ("All files", "*.*")]).pack(fill="x", pady=3)
        ttk.Button(self, text="評価を集計", command=self.start).pack(anchor="w", pady=6)
        self.table = ttk.Treeview(self, columns=("profile", "preset", "runs", "change", "edge", "score", "best"), show="headings", height=10)
        for key, title in (("profile", "profile"), ("preset", "強調対象"), ("runs", "実行数"), ("change", "平均変化"), ("edge", "平均輪郭変化"), ("score", "平均score"), ("best", "最良score")): self.table.heading(key, text=title); self.table.column(key, width=110, anchor="w")
        self.table.pack(fill="x", pady=5); self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True)

    # {
    #   "責務": "Touka評価履歴の集計をworker threadで開始する。",
    #   "処理": ["runをdaemon threadとして起動する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def start(self): threading.Thread(target=self.run, daemon=True).start()

    # {
    #   "責務": "評価履歴を読み集計しtableと任意のMarkdown fileへ反映する。",
    #   "処理": ["履歴を読む・profile/preset別に集計する", "tableを更新し出力先指定時はMarkdownを保存する", "件数・不正record数・失敗をログへ報告する"],
    #   "引数": [],
    #   "戻り値": []
    # }
    def run(self):
        try:
            evaluator = ToukaEvaluationReport(); records, errors = evaluator.read(self.history_dir.get().strip()); rows = evaluator.summarize(records)
            for item in self.table.get_children(): self.table.delete(item)
            for row in rows: self.table.insert("", "end", values=(row["profile"], row["object_preset"], row["runs"], f"{row['mean_change']:.3f}", f"{row['mean_edge_change']:.3f}", f"{row['mean_score']:.3f}", f"{row['best_score']:.3f}"))
            output = self.output.get().strip()
            if output: evaluator.write_markdown(output, rows)
            self.logbox.log(f"評価 {len(records)}件を{len(rows)}グループへ集計しました" + (f"（不正行 {errors}件）" if errors else ""))
        except Exception as error: self.logbox.log(f"評価集計エラー: {error}")
