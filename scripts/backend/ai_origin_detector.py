"""Local Hugging Face adapter for AI-origin image classification."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError(f"未対応の推論デバイスです: {device}")
        self.model_id = model_id.strip()
        if not self.model_id:
            raise ValueError("モデルIDを指定してください")
        self.device = device
        self.pipeline = None
        self.load_error = None
        self.external_process = None

    # {
    # 責務: [_load_pipeline: 推論pipelineを遅延ロードする]
    # 処理: [1: 推論pipelineを遅延ロードする]
    # 引数: [self]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def _load_pipeline(self):
        if self.pipeline is not None:
            return self.pipeline
        if self.load_error is not None:
            raise RuntimeError(
                f"判定モデルの初期化に失敗済みです: {self.load_error}"
            ) from self.load_error
        try:
            self.pipeline = self._create_pipeline()
        except Exception as error:
            self.load_error = error
            raise RuntimeError(f"判定モデルの初期化に失敗しました: {error}") from error
        return self.pipeline

    # {
    # 責務: [_create_pipeline: モデル依存をロードして推論器を生成する]
    # 処理: [1: 凍結版は外部Python workerを起動する, 2: ソース版は依存とdeviceを解決してpipelineを構築する]
    # 引数: [self]
    # 戻り値: [image-classification pipeline]
    # }
    def _create_pipeline(self):
        frozen = getattr(sys, "frozen", False)
        application_root = (
            Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parents[2]
        )
        cache_directory = application_root / "user_data" / "cache" / "ai_origin"
        os.environ.setdefault("HF_HOME", str(cache_directory))
        if frozen:
            return self._start_external_worker(cache_directory)
        try:
            import torch
            from transformers import pipeline
        except ImportError as error:
            message = (
                "AI画像判定には PyTorch、Transformers、Pillow が必要です。"
                "対応するPython環境へ追加してください。"
            )
            raise RuntimeError(message) from error
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDAが利用できません。CPUを選択してください。")
        selected_device = (
            0
            if self.device == "cuda" or (self.device == "auto" and torch.cuda.is_available())
            else -1
        )
        return pipeline(
            "image-classification",
            model=self.model_id,
            device=selected_device,
            top_k=None,
        )

    # {
    # 責務: [_start_external_worker: 凍結アプリ用の外部Python推論workerを起動する]
    # 処理: [1: 設定済みPythonでworkerを起動し初期化結果を確認する]
    # 引数: [self]
    # 戻り値: [worker初期化後にTrue]
    # }
    def _start_external_worker(self, cache_directory: Path) -> bool:
        from ..runtime_python import preferred_python

        configured = os.environ.get("KADOKA_AI_ORIGIN_PYTHON", "").strip()
        python = Path(configured).expanduser() if configured else preferred_python()
        if not python.is_file():
            raise RuntimeError(f"AI判定用Pythonが見つかりません: {python}")
        worker = subprocess.Popen(
            [
                str(python),
                "-u",
                "-c",
                _EXTERNAL_WORKER_CODE,
                self.model_id,
                self.device,
                str(cache_directory),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self.external_process = worker
        response = worker.stdout.readline() if worker.stdout else ""
        try:
            ready = json.loads(response)
        except json.JSONDecodeError as error:
            worker.terminate()
            worker.wait(timeout=5)
            raise RuntimeError(
                "外部PythonのAI判定workerから初期化結果を取得できません。"
                "KADOKA_AI_ORIGIN_PYTHON環境の依存関係を確認してください。"
            ) from error
        if not isinstance(ready, dict) or ready.get("ready") is not True:
            worker.wait(timeout=5)
            detail = (
                ready.get("error", "workerがreadyを返しませんでした")
                if isinstance(ready, dict)
                else "worker応答が不正です"
            )
            raise RuntimeError(f"外部PythonでAI判定器を初期化できません: {detail}")
        return True

    # {
    # 責務: [_external_ai_score: 外部Python workerから画像のAIスコアを取得する]
    # 処理: [1: 画像pathをworkerへ送りスコア応答を読む]
    # 引数: [self, path]
    # 戻り値: [0から1までのAI生成スコア]
    # }
    def _external_ai_score(self, path: Path) -> float:
        worker = self.external_process
        if worker is None or worker.stdin is None or worker.stdout is None:
            raise RuntimeError("外部PythonのAI判定workerが起動していません")
        worker.stdin.write(json.dumps({"path": str(path)}, ensure_ascii=False) + "\n")
        worker.stdin.flush()
        response = worker.stdout.readline()
        if not response:
            raise RuntimeError("外部PythonのAI判定workerが応答せず終了しました")
        payload = json.loads(response)
        if payload.get("error"):
            raise RuntimeError(f"外部Pythonで画像を判定できません: {payload['error']}")
        return float(payload["score"])

    # {
    # 責務: [_close_external_worker: 凍結アプリ用の推論workerを終了する]
    # 処理: [1: 終了指示を送りプロセスを停止する]
    # 引数: [self]
    # 戻り値: []
    # }
    def _close_external_worker(self) -> None:
        worker = self.external_process
        self.external_process = None
        if worker is None:
            return
        try:
            if worker.stdin:
                worker.stdin.write('{"command":"shutdown"}\n')
                worker.stdin.flush()
                worker.stdin.close()
            worker.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            worker.terminate()
            worker.wait(timeout=5)

    # {
    # 責務: [close: 判定処理終了後に外部Python workerを閉じる]
    # 処理: [1: 外部Python workerを安全に終了する]
    # 引数: [self]
    # 戻り値: []
    # }
    def close(self) -> None:
        self._close_external_worker()

    # {
    # 責務: [ai_score: 推論対象画像のAI生成スコアを取得する]
    # 処理: [1: 推論対象画像のAI生成スコアを取得する]
    # 引数: [self, path]
    # 戻り値: [宣言の戻り値を返す]
    # }
    def ai_score(self, path: Path) -> float:
        if getattr(sys, "frozen", False):
            self._load_pipeline()
            return self._external_ai_score(path)
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


_EXTERNAL_WORKER_CODE = r"""import json
import os
import sys

model_id, requested_device, cache_directory = sys.argv[1:4]
os.environ["HF_HOME"] = cache_directory
try:
    import torch
    from PIL import Image
    from transformers import pipeline

    if requested_device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDAが利用できません。CPUを選択してください。")
    device = 0 if requested_device == "cuda" or (requested_device == "auto" and torch.cuda.is_available()) else -1
    detector = pipeline("image-classification", model=model_id, device=device, top_k=None)
    print(json.dumps({"ready": True}, ensure_ascii=False), flush=True)
except Exception as error:
    print(json.dumps({"error": str(error)}, ensure_ascii=False), flush=True)
    raise SystemExit(1)

for line in sys.stdin:
    request = json.loads(line)
    if request.get("command") == "shutdown":
        break
    try:
        with Image.open(request["path"]) as image:
            predictions = detector(image.convert("RGB"))
        ai_predictions = [
            item for item in predictions
            if item["label"].strip().casefold() in {"ai", "artificial", "generated", "ai-generated"}
        ]
        if len(ai_predictions) != 1:
            raise ValueError("モデルのAIラベルを一意に特定できません")
        score = float(ai_predictions[0]["score"])
        if not 0 <= score <= 1:
            raise ValueError("モデルが範囲外のスコアを返しました")
        print(json.dumps({"score": score}), flush=True)
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), flush=True)
"""
