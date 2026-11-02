from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image


# {
#   責務: [ToukaEvaluator: Touka image outputs and candidate ranking metricsを評価・記録する]
#   処理: [image pairsを比較し、candidate scoresをcollectしてJSON historyへ保存する]
#   フィールド: [IMAGE_SUFFIXES and evaluation operations]
# }
class ToukaEvaluator:
    """Evaluate Touka image changes and persist evaluation history."""

    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}

    # {
    #   責務: [_metrics: source/output image pairのpixel and edge change metricsを算出する]
    #   処理: [RGB convert, resize, numpy arrays, luminance and edge differencesを計算する]
    #   引数: [source, output]
    #   戻り値: [dict[str, float]]
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
    #   責務: [evaluate_images: single imagesまたはmatching output directoryのimage pairsを集計する]
    #   処理: [enhanced filename pairsを探し、per-image metricsをaverageする]
    #   引数: [source, output]
    #   戻り値: [dict]
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
    #   責務: [evaluate_candidates: output tree内candidate ranking/scores JSONからscore metricsを得る]
    #   処理: [first available ranking fileをparseしてscore and temporal stabilityを集計する]
    #   引数: [output]
    #   戻り値: [dict]
    # }
    def evaluate_candidates(self, output: Path) -> dict:
        paths = list(output.rglob("candidate_ranking.json")) + list(output.rglob("candidate_scores.json")) if output.is_dir() else []
        if not paths: return {"candidate_count": 0}
        entries = json.loads(paths[0].read_text(encoding="utf-8")); entries = entries if isinstance(entries, list) else []
        scores = [float(item.get("score", 0.0)) for item in entries if isinstance(item, dict)]
        stability = [float(item.get("temporal_shape_consistency", 0.0)) for item in entries if isinstance(item, dict)]
        return {"candidate_count": len(scores), "mean_score": float(np.mean(scores)) if scores else 0.0, "best_score": max(scores, default=0.0), "mean_temporal_stability": float(np.mean(stability)) if stability else 0.0}

    # {
    #   責務: [evaluate: paths and Touka profile detailsからevaluation recordを構築する]
    #   処理: [timestamp, source/output metadata, image metrics, and candidate metricsをmergeする]
    #   引数: [source, output, profile, object_preset]
    #   戻り値: [dict]
    # }
    def evaluate(self, source: str, output: str, profile: str, object_preset: str) -> dict:
        source_path, output_path = Path(source), Path(output)
        result = {"timestamp": datetime.now().isoformat(timespec="seconds"), "profile": profile, "object_preset": object_preset, "source": str(source_path), "output": str(output_path)}
        result.update(self.evaluate_images(source_path, output_path)); result.update(self.evaluate_candidates(output_path)); return result

    # {
    #   責務: [write_history: evaluation recordをappend-only JSONL and latest JSONへ保存する]
    #   処理: [history directoryを作成し、latest recordを更新する]
    #   引数: [history_dir, record]
    #   戻り値: [Path]
    # }
    def write_history(self, history_dir: str, record: dict) -> Path:
        destination = Path(history_dir); destination.mkdir(parents=True, exist_ok=True); path = destination / "touka_evaluation.jsonl"
        with path.open("a", encoding="utf-8") as target: target.write(json.dumps(record, ensure_ascii=False) + "\n")
        (destination / "latest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); return path
