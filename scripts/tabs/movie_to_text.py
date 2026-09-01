from __future__ import annotations

import base64
from pathlib import Path

from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore


class MovieToTextTab(ttk.Frame):
    """動画の代表フレームをPixAI Taggerへ送り、共通タグをプロンプト化する。"""

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.stop_event = threading.Event()
        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar(value=str(USER_DATA_DIR / "output" / "movie_to_text" / "movie_tags.txt"))
        self.api_url = tk.StringVar(value=PIXAI_TAGGER_API_URL)
        self.model = tk.StringVar(value=PIXAI_TAGGER_MODEL)
        self.frame_count = tk.IntVar(value=12)
        self.threshold = tk.DoubleVar(value=0.35)
        self.minimum_coverage = tk.DoubleVar(value=0.5)
        self.preset_store = PresetStore("movie_to_text")
        self.preset_name = tk.StringVar()
        self._build()

    def _build(self):
        LabeledPathRow(self, "入力動画", self.input_file, mode="file", filetypes=[("動画", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("All files", "*.*")]).pack(fill="x", pady=3)
        LabeledPathRow(self, "出力TXT", self.output_file, mode="save", filetypes=[("Text files", "*.txt"), ("All files", "*.*")]).pack(fill="x", pady=3)
        api_row = ttk.Frame(self); api_row.pack(fill="x", pady=3)
        ttk.Label(api_row, text="PixAI API", width=16).pack(side="left")
        ttk.Entry(api_row, textvariable=self.api_url).pack(side="left", fill="x", expand=True)
        ttk.Button(api_row, text="API起動", command=self.start_api).pack(side="left", padx=4)
        ttk.Button(api_row, text="API停止", command=self.stop_api).pack(side="left")
        options = ttk.Frame(self); options.pack(fill="x", pady=3)
        for label, variable, width in (("モデル", self.model, 32), ("フレーム数", self.frame_count, 6), ("閾値", self.threshold, 6), ("出現率", self.minimum_coverage, 6)):
            ttk.Label(options, text=label).pack(side="left", padx=(0, 4))
            ttk.Entry(options, textvariable=variable, width=width).pack(side="left", padx=(0, 10))
        buttons = ttk.Frame(self); buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="動画をタグ化", command=self.start).pack(side="left")
        ttk.Button(buttons, text="停止", command=self.stop).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18); self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    def start_api(self):
        _safe_thread(self.logbox, PIXAI_TAGGER_SERVER.start, self.logbox.log)

    def stop_api(self):
        _safe_thread(self.logbox, PIXAI_TAGGER_SERVER.stop, self.logbox.log)

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def _preset_values(self):
        return {"input_file": self.input_file.get(), "output_file": self.output_file.get(), "api_url": self.api_url.get(), "model": self.model.get(), "frame_count": self.frame_count.get(), "threshold": self.threshold.get(), "minimum_coverage": self.minimum_coverage.get()}

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), self._preset_values()); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (("input_file", self.input_file), ("output_file", self.output_file), ("api_url", self.api_url), ("model", self.model), ("frame_count", self.frame_count), ("threshold", self.threshold), ("minimum_coverage", self.minimum_coverage)):
                if key in values: variable.set(values[key])
            self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    @staticmethod
    def _scores(result):
        tags = result.get("tags", result) if isinstance(result, dict) else result
        if isinstance(tags, dict):
            return {str(tag).strip(): float(score) for tag, score in tags.items() if isinstance(score, (int, float)) and str(tag).strip()}
        return {tag: 1.0 for tag in extract_tagger_tags(result)}

    @staticmethod
    def aggregate(frame_scores, minimum_coverage, threshold):
        totals, appearances = {}, {}
        for scores in frame_scores:
            for tag, score in scores.items():
                totals[tag] = totals.get(tag, 0.0) + score
                appearances[tag] = appearances.get(tag, 0) + 1
        count = max(1, len(frame_scores))
        return [tag for tag in sorted(totals, key=lambda tag: (-appearances[tag], -totals[tag], tag.casefold())) if appearances[tag] / count >= minimum_coverage and totals[tag] / appearances[tag] >= threshold]

    def start(self):
        self.stop_event.clear()
        _safe_thread(self.logbox, self.run)

    def stop(self):
        self.stop_event.set(); self.logbox.log("停止要求を送信しました")

    def run(self):
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError("cv2 が見つかりません。Tabbed GUIをrun.batから起動してください") from error
        if requests is None:
            raise RuntimeError("requests がインストールされていません")
        source = Path(self.input_file.get().strip())
        if not source.is_file():
            raise ValueError(f"入力動画がありません: {source}")
        count = max(1, int(self.frame_count.get()))
        coverage = min(1.0, max(0.0, float(self.minimum_coverage.get())))
        threshold = float(self.threshold.get())
        capture = cv2.VideoCapture(str(source))
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total < 1:
            capture.release(); raise ValueError(f"動画を読めません: {source}")
        indices = sorted({round((total - 1) * index / max(1, count - 1)) for index in range(count)})
        scores = []
        for order, index in enumerate(indices, 1):
            if self.stop_event.is_set(): break
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok: continue
            ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            if not ok: continue
            payload = {"image": base64.b64encode(encoded.tobytes()).decode("ascii"), "model": self.model.get().strip(), "threshold": threshold, "character_threshold": threshold}
            response = requests.post(self.api_url.get().strip(), json=payload, timeout=300)
            response.raise_for_status()
            scores.append(self._scores(response.json()))
            self.logbox.log(f"タグ取得: {order}/{len(indices)} frame={index}")
        capture.release()
        tags = self.aggregate(scores, coverage, threshold)
        output = Path(self.output_file.get().strip())
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(", ".join(tags) + "\n", encoding="utf-8")
        self.logbox.log(f"完了: {len(scores)}フレーム / {len(tags)}タグ / {output}")
