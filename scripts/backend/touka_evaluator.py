from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image


# {
# 責務: [ToukaEvaluator: 入出力画像の変化量と候補順位を評価して履歴を保存する]
# フィールド: []
# 処理: [1: 画像変化と候補scoreを算出する, 2: 評価recordをJSON形式で保持する]
# }
class ToukaEvaluator:
    """Evaluate Touka image changes and persist evaluation history."""

    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

    # {
    # 責務: [_metrics: 対応するsource/output画像1組の変化指標を計算する]
    # 処理: [1: RGB画像を読み込み同一寸法に揃える, 2: pixel差・輝度ばらつき・輪郭差を求める]
    # 引数: [source: 元画像path, output: 処理後画像path]
    # 戻り値: [平均絶対変化・輝度標準偏差・edge変化の指標]
    # }
    @staticmethod
    def _metrics(source: Path, output: Path) -> dict[str, float]:
        with Image.open(source).convert("RGB") as source_image, Image.open(output).convert("RGB") as output_image:
            output_image = output_image.resize(source_image.size)
            first = np.asarray(source_image, dtype=np.float32)
            second = np.asarray(output_image, dtype=np.float32)
        first_gray = first.mean(axis=2); second_gray = second.mean(axis=2)
        first_edge = np.abs(np.diff(first_gray, axis=0)).mean() + np.abs(np.diff(first_gray, axis=1)).mean()
        second_edge = np.abs(np.diff(second_gray, axis=0)).mean() + np.abs(np.diff(second_gray, axis=1)).mean()
        return {"mean_absolute_change": float(np.abs(second - first).mean()), "source_luminance_std": float(first_gray.std()), "output_luminance_std": float(second_gray.std()), "edge_change": float(second_edge - first_edge)}

    # {
    # 責務: [evaluate_images: sourceと対応する処理後画像群の変化指標を集計する]
    # 処理: [1: 単一file対または相対path対応画像を選ぶ, 2: 各pairの指標を計算する,
    # 3: 全体平均と画像数を返す]
    # 引数: [source: 元画像fileまたはdirectory, output: 処理後画像fileまたはdirectory]
    # 戻り値: [画像数と集約した変化指標]
    # }
    def evaluate_images(self, source: Path, output: Path) -> dict:
        pairs = []
        if source.is_file() and output.is_file(): pairs = [(source, output)]
        elif source.is_dir() and output.is_dir():
            for path in source.rglob("*"):
                if path.is_file() and path.suffix.lower() in self.IMAGE_SUFFIXES:
                    relative = path.relative_to(source); candidate = output / relative.with_name(relative.stem + "_enhanced" + relative.suffix)
                    if candidate.is_file(): pairs.append((path, candidate))
        values = [self._metrics(first, second) for first, second in pairs]
        if not values: return {"image_count": 0, "mean_absolute_change": 0.0, "source_luminance_std": 0.0, "output_luminance_std": 0.0, "edge_change": 0.0}
        return {"image_count": len(values), **{key: float(np.mean([item[key] for item in values])) for key in values[0]}}

    # {
    # 責務: [evaluate_candidates: 出力配下の候補rank fileからscoreと安定性を集計する]
    # 処理: [1: 対応JSONを探す, 2: 候補scoreとtemporal consistencyを読む,
    # 3: count・平均・最大値を返す]
    # 引数: [output: 候補評価JSONを含む出力directory]
    # 戻り値: [候補数とscore・時間安定性の集計]
    # }
    def evaluate_candidates(self, output: Path) -> dict:
        paths = list(output.rglob("candidate_ranking.json")) + list(output.rglob("candidate_scores.json")) if output.is_dir() else []
        if not paths: return {"candidate_count": 0}
        entries = json.loads(paths[0].read_text(encoding="utf-8")); entries = entries if isinstance(entries, list) else []
        scores = [float(item.get("score", 0.0)) for item in entries if isinstance(item, dict)]
        stability = [float(item.get("temporal_shape_consistency", 0.0)) for item in entries if isinstance(item, dict)]
        return {"candidate_count": len(scores), "mean_score": float(np.mean(scores)) if scores else 0.0, "best_score": max(scores, default=0.0), "mean_temporal_stability": float(np.mean(stability)) if stability else 0.0}

    # {
    # 責務: [evaluate: 画像指標と候補指標を1つのTouka評価recordへまとめる]
    # 処理: [1: pathと評価条件を記録する, 2: image・candidate評価を加える]
    # 引数: [source: 元画像path, output: 処理結果path, profile: 使用profile, object_preset: 強調対象preset]
    # 戻り値: [timestamp・条件・画像・候補指標を含む評価record]
    # }
    def evaluate(self, source: str, output: str, profile: str, object_preset: str) -> dict:
        source_path, output_path = Path(source), Path(output)
        result = {"timestamp": datetime.now().isoformat(timespec="seconds"), "profile": profile, "object_preset": object_preset, "source": str(source_path), "output": str(output_path)}
        result.update(self.evaluate_images(source_path, output_path)); result.update(self.evaluate_candidates(output_path)); return result

    # {
    # 責務: [write_history: 評価recordを追記履歴と最新snapshotへ保存する]
    # 処理: [1: 履歴directoryを作る, 2: JSONLへrecordを追記する,
    # 3: latest.jsonを置換して履歴pathを返す]
    # 引数: [history_dir: 評価履歴directory, record: 保存する評価record]
    # 戻り値: [JSONL履歴file path]
    # }
    def write_history(self, history_dir: str, record: dict) -> Path:
        destination = Path(history_dir); destination.mkdir(parents=True, exist_ok=True); path = destination / "touka_evaluation.jsonl"
        with path.open("a", encoding="utf-8") as target: target.write(json.dumps(record, ensure_ascii=False) + "\n")
        (destination / "latest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); return path
