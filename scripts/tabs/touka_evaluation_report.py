from __future__ import annotations

import threading

from ..context import *
from ..backend.touka_evaluation_report import ToukaEvaluationReport
from ..services import LogBox, LabeledPathRow


# {
#   責務: [ToukaEvaluationReportTab: Touka evaluation historyをgrouped table and Markdown reportで表示するtab]
#   処理: [collect history/output paths and present evaluator summary/error counts]
#   フィールド: [history_dir, output, table, logbox]
# }
class ToukaEvaluationReportTab(ttk.Frame):
    """Display and export grouped Touka evaluation history."""

    # {
    #   責務: [__init__: history/output path variables and UIを初期化する]
    #   処理: [create Tk variables and build widgets]
    #   引数: [master]
    #   戻り値: [処理結果]
    # }
    def __init__(self, master):
        super().__init__(master, padding=10)
        self.history_dir = tk.StringVar()
        self.output = tk.StringVar()
        self._build()

    # {
    #   責務: [_build: history/output controls, evaluation action, grouped table, and logを構築する]
    #   処理: [create browseable paths and summary columns]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def _build(self):
        LabeledPathRow(self, "評価履歴フォルダ", self.history_dir, mode="dir").pack(
            fill="x", pady=3
        )
        LabeledPathRow(
            self,
            "Markdown出力",
            self.output,
            mode="save",
            filetypes=[("Markdown", "*.md"), ("All files", "*.*")],
        ).pack(fill="x", pady=3)
        ttk.Button(self, text="評価を集計", command=self.start).pack(anchor="w", pady=6)
        self.table = ttk.Treeview(
            self,
            columns=("profile", "preset", "runs", "change", "edge", "score", "best"),
            show="headings",
            height=10,
        )
        for key, title in (
            ("profile", "profile"),
            ("preset", "強調対象"),
            ("runs", "実行数"),
            ("change", "平均変化"),
            ("edge", "平均輪郭変化"),
            ("score", "平均score"),
            ("best", "最良score"),
        ):
            self.table.heading(key, text=title)
            self.table.column(key, width=110, anchor="w")
        self.table.pack(fill="x", pady=5)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)

    # {
    #   責務: [start: evaluation report aggregationをdaemon workerで開始する]
    #   処理: [spawn run without blocking Tk]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def start(self):
        threading.Thread(target=self.run, daemon=True).start()

    # {
    #   責務: [run: history recordsをread and summarizeしてtable and optional Markdownへ出力する]
    #   処理: [replace table rows, write requested report file, and log invalid record/error counts]
    #   引数: [なし]
    #   戻り値: [処理結果]
    # }
    def run(self):
        try:
            evaluator = ToukaEvaluationReport()
            records, errors = evaluator.read(self.history_dir.get().strip())
            rows = evaluator.summarize(records)
            for item in self.table.get_children():
                self.table.delete(item)
            for row in rows:
                self.table.insert(
                    "",
                    "end",
                    values=(
                        row["profile"],
                        row["object_preset"],
                        row["runs"],
                        f"{row['mean_change']:.3f}",
                        f"{row['mean_edge_change']:.3f}",
                        f"{row['mean_score']:.3f}",
                        f"{row['best_score']:.3f}",
                    ),
                )
            output = self.output.get().strip()
            if output:
                evaluator.write_markdown(output, rows)
            self.logbox.log(
                f"評価 {len(records)}件を{len(rows)}グループへ集計しました"
                + (f"（不正行 {errors}件）" if errors else "")
            )
        except Exception as error:
            self.logbox.log(f"評価集計エラー: {error}")
