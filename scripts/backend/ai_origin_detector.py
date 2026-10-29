"""Local Hugging Face adapter for AI-origin image classification."""

from __future__ import annotations

import os
from pathlib import Path


# {
# 責務: [AnimeAIDetector: OSSモデルによる画像判定を提供する]
# フィールド: [状態: OSSモデルによる画像判定を提供する]
# }
class AnimeAIDetector:
    # {
    # 責務: [__init__: 依存と設定値を初期化する]
    # 処理: [1: 依存と設定値を初期化する]
    # 引数: [self, model_id, device]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def __init__(self, model_id: str, device: str):
        # {
        #   責務: [__init__: 指定モデルと推論デバイスを初期化する]
        #   引数: [self: detector, model_id: Hugging Face model ID, device: auto/cpu/cuda]
        #   戻り値: []
        # }
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError(f"未対応の推論デバイスです: {device}")
        self.model_id = model_id.strip()
        if not self.model_id:
            raise ValueError("モデルIDを指定してください")
        self.device = device
        self.pipeline = None

    # {
    # 責務: [_load_pipeline: 推論pipelineを遅延ロードする]
    # 処理: [1: 推論pipelineを遅延ロードする]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def _load_pipeline(self):
        # {
        #   責務: [_load_pipeline: 初回の画像推論時にモデル依存をロードする]
        #   引数: [self: detector]
        #   戻り値: [Transformers image-classification pipeline]
        # }
        if self.pipeline is not None:
            return self.pipeline
        os.environ.setdefault(
            "HF_HOME",
            str(Path(__file__).resolve().parents[2] / "user_data" / "cache" / "ai_origin"),
        )
        try:
            import torch
            from transformers import pipeline
        except ImportError as error:
            raise RuntimeError(
                "AI画像判定には PyTorch、Transformers、Pillow が必要です。"
                "対応するPython環境へ追加してください。"
            ) from error
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDAが利用できません。CPUを選択してください。")
        selected_device = (
            0
            if self.device == "cuda" or (self.device == "auto" and torch.cuda.is_available())
            else -1
        )
        self.pipeline = pipeline(
            "image-classification",
            model=self.model_id,
            device=selected_device,
            top_k=None,
        )
        return self.pipeline

    # {
    # 責務: [ai_score: 推論対象画像のAI生成スコアを取得する]
    # 処理: [1: 推論対象画像のAI生成スコアを取得する]
    # 引数: [self, path]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def ai_score(self, path: Path) -> float:
        # {
        #   責務: [ai_score: 画像1枚のAI生成ラベル確率を返す]
        #   引数: [self: detector, path: 推論対象画像]
        #   戻り値: [AI生成スコア。ラベルが一意でない場合は例外]
        # }
        from PIL import Image

        with Image.open(path) as image:
            predictions = self._load_pipeline()(image.convert("RGB"))
        ai_predictions = [
            item
            for item in predictions
            if item["label"].strip().casefold() in {"ai", "artificial", "generated", "ai-generated"}
        ]
        if len(ai_predictions) != 1:
            labels = [item.get("label", "") for item in predictions]
            raise ValueError(f"モデルのAIラベルを特定できません: {labels}")
        score = float(ai_predictions[0]["score"])
        if not 0 <= score <= 1:
            raise ValueError(f"モデルが範囲外のスコアを返しました: {score}")
        return score
