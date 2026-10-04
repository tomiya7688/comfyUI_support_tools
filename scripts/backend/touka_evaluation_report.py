from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


# {
# 責務: [ToukaEvaluationReport: ToukaのJSONL評価履歴を集計してMarkdown化する]
# フィールド: []
# 処理: [1: 履歴recordを読み込む, 2: profileとpreset単位で指標を集計する, 3: reportを保存する]
# }
class ToukaEvaluationReport:
    """Summarize Touka JSONL evaluation history by profile and preset."""

    # {
    # 責務: [read: Touka評価JSONL履歴を読み込み不正行数を数える]
    # 処理: [1: 履歴fileの存在を確認する, 2: JSON行を解析してobject recordを集める,
    # 3: 不正JSON行数と共に返す]
    # 引数: [history_dir: 履歴fileを含むdirectory]
    # 戻り値: [有効record一覧とJSON parse失敗行数]
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
    # 責務: [summarize: 評価recordをprofile・対象preset別に集計する]
    # 処理: [1: profileとpresetでrecordをgroup化する, 2: 指標の平均とbest scoreを算出する,
    # 3: 表示順の集計rowを返す]
    # 引数: [records: 読み込んだ評価record一覧]
    # 戻り値: [profile・preset別の集計row一覧]
    # }
    def summarize(self, records: list[dict]) -> list[dict]:
        groups = defaultdict(list)
        for record in records: groups[(str(record.get("profile", "")), str(record.get("object_preset", "")))].append(record)
        rows = []
        for (profile, preset), values in sorted(groups.items()):
            # {
            # 責務: [average: 現在のgroup内にある指定指標の平均を計算する]
            # 処理: [1: 数値値だけ抽出する, 2: 値があれば平均、なければ0を返す]
            # 引数: [key: 平均対象record field名]
            # 戻り値: [対象指標の平均値]
            # }
            def average(key):
                numbers = [float(item[key]) for item in values if isinstance(item.get(key), (int, float))]
                return sum(numbers) / len(numbers) if numbers else 0.0
            rows.append({"profile": profile, "object_preset": preset, "runs": len(values), "mean_change": average("mean_absolute_change"), "mean_edge_change": average("edge_change"), "mean_score": average("mean_score"), "best_score": max((float(item.get("best_score", 0.0)) for item in values), default=0.0)})
        return rows

    # {
    # 責務: [write_markdown: 集計rowを表形式のMarkdown reportへ保存する]
    # 処理: [1: 出力directoryを作る, 2: 評価表を整形する, 3: UTF-8で書き込む]
    # 引数: [output: Markdown出力path, rows: profile別集計row一覧]
    # 戻り値: [書き込んだMarkdown path]
    # }
    def write_markdown(self, output: str, rows: list[dict]) -> Path:
        path = Path(output); path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Touka評価サマリー", "", "| profile | 強調対象 | 実行数 | 平均変化 | 平均輪郭変化 | 平均score | 最良score |", "|---|---|---:|---:|---:|---:|---:|"]
        lines.extend(f"| {row['profile']} | {row['object_preset']} | {row['runs']} | {row['mean_change']:.3f} | {row['mean_edge_change']:.3f} | {row['mean_score']:.3f} | {row['best_score']:.3f} |" for row in rows)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8"); return path
