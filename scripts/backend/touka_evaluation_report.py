from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


# {
#   責務: [ToukaEvaluationReport: Touka JSONL evaluation historyをsummary tableへ集約する]
#   処理: [invalid JSONL rowsをcountし、profile/preset単位metricsをMarkdown出力する]
#   フィールド: [stateless report operations]
# }
class ToukaEvaluationReport:
    """Summarize Touka JSONL evaluation history by profile and preset."""

    # {
    #   責務: [read: evaluation JSONL historyを読み、valid dict records and parse error countを返す]
    #   処理: [missing historyをraiseし、malformed JSON rowsをskipする]
    #   引数: [history_dir]
    #   戻り値: [tuple[list[dict], int]]
    # }
    def read(self, history_dir: str) -> tuple[list[dict], int]:
        path = Path(history_dir) / "touka_evaluation.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"評価履歴が見つかりません: {path}")
        records = []; errors = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict): records.append(value)
            except json.JSONDecodeError: errors += 1
        return records, errors

    # {
    #   責務: [summarize: evaluation recordsをprofile and object presetごとに集約する]
    #   処理: [runs, average change/score metrics, and best scoreをcalculateする]
    #   引数: [records]
    #   戻り値: [list[dict]]
    # }
    def summarize(self, records: list[dict]) -> list[dict]:
        groups = defaultdict(list)
        for record in records: groups[(str(record.get("profile", "")), str(record.get("object_preset", "")))].append(record)
        rows = []
        for (profile, preset), values in sorted(groups.items()):
            # {
            #   責務: [average: one metric keyのnumeric record valuesのmeanを計算する]
            #   処理: [non-numeric or absent valuesをskipし、empty inputでは0を返す]
            #   引数: [key]
            #   戻り値: [float]
            # }
            def average(key):
                numbers = [float(item[key]) for item in values if isinstance(item.get(key), (int, float))]
                return sum(numbers) / len(numbers) if numbers else 0.0
            rows.append({"profile": profile, "object_preset": preset, "runs": len(values), "mean_change": average("mean_absolute_change"), "mean_edge_change": average("edge_change"), "mean_score": average("mean_score"), "best_score": max((float(item.get("best_score", 0.0)) for item in values), default=0.0)})
        return rows

    # {
    #   責務: [write_markdown: summary rowsをMarkdown tableとしてoutputへ保存する]
    #   処理: [parent directoriesを作りformatted metric tableを書き込む]
    #   引数: [output, rows]
    #   戻り値: [Path]
    # }
    def write_markdown(self, output: str, rows: list[dict]) -> Path:
        path = Path(output); path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Touka評価サマリー", "", "| profile | 強調対象 | 実行数 | 平均変化 | 平均輪郭変化 | 平均score | 最良score |", "|---|---|---:|---:|---:|---:|---:|"]
        lines.extend(f"| {row['profile']} | {row['object_preset']} | {row['runs']} | {row['mean_change']:.3f} | {row['mean_edge_change']:.3f} | {row['mean_score']:.3f} | {row['best_score']:.3f} |" for row in rows)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8"); return path
