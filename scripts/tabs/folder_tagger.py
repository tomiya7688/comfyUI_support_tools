from ..context import *
from ..context import _safe_thread
from ..services import *
from ..widgets.preset_store import PresetStore
from ..backend.taggui_controller import TagGUIController

class FolderTaggerTab(ttk.Frame):
    TAGGER_PRESETS = {
        "PixAI Tagger": (PIXAI_TAGGER_API_URL, PIXAI_TAGGER_MODEL),
    }
    DEFAULT_OUTPUT = str(
        WILDCARDS_DIR
        / "many_prompt_by_artist"
        / "folder_tags.txt"
    )
    DEFAULT_EXCLUDE = (
        "worst quality, low quality, normal quality, lowres, blurry, jpeg artifacts, "
        "bad anatomy, bad hands, extra fingers, missing fingers, text, error, signature, "
        "watermark, username, artist name, animal ears, furry, censored, sfw"
    )
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.stop_event = threading.Event()
        self.worker_thread = None
        self.taggui_controller = TagGUIController()
        self.preset_store = PresetStore("folder_tagger")
        self.preset_name = tk.StringVar()
        self.input_dir = tk.StringVar()
        self.output_file = tk.StringVar(value=self.DEFAULT_OUTPUT)
        default_tagger = "PixAI Tagger"
        default_api_url, default_model = self.TAGGER_PRESETS[default_tagger]
        self.tagger_kind = tk.StringVar(value=default_tagger)
        self.api_url = tk.StringVar(value=default_api_url)
        self.model = tk.StringVar(value=default_model)
        self.threshold = tk.StringVar(value="0.35")
        self.character_threshold = tk.StringVar(value="0.85")
        self.timeout = tk.StringVar(value="300")
        self.additional = tk.StringVar(value="")
        self.exclude = tk.StringVar(value=self.DEFAULT_EXCLUDE)
        self.recursive = tk.BooleanVar(value=True)
        self.overwrite = tk.BooleanVar(value=True)
        self.gif_average = tk.BooleanVar(value=True)
        self.character_crop = tk.BooleanVar(value=False)
        self._build()

    def _build(self):
        paths = ttk.LabelFrame(self, text="入出力", padding=8)
        paths.pack(fill="x")
        LabeledPathRow(paths, "画像フォルダ", self.input_dir, mode="dir").pack(fill="x", pady=3)
        LabeledPathRow(
            paths,
            "出力TXT",
            self.output_file,
            mode="save",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        ).pack(fill="x", pady=3)

        api_frame = ttk.LabelFrame(self, text="Tagger", padding=8)
        api_frame.pack(fill="x", pady=6)
        kind_row = ttk.Frame(api_frame)
        kind_row.pack(fill="x", pady=2)
        ttk.Label(kind_row, text="Tagger", width=16).pack(side="left")
        tagger_combo = ttk.Combobox(
            kind_row,
            textvariable=self.tagger_kind,
            values=list(self.TAGGER_PRESETS),
            state="readonly",
            width=24,
        )
        tagger_combo.pack(side="left")
        tagger_combo.bind("<<ComboboxSelected>>", self._apply_tagger_preset)
        ttk.Button(kind_row, text="PixAI API起動", command=self.start_pixai_api).pack(side="left", padx=(12, 4))
        ttk.Button(kind_row, text="PixAI API停止", command=self.stop_pixai_api).pack(side="left", padx=4)
        ttk.Button(kind_row, text="TagGUIを起動（手動タグ付け）", command=self.start_taggui).pack(side="left", padx=(12, 4))
        ttk.Button(kind_row, text="TagGUIを停止", command=self.stop_taggui).pack(side="left", padx=4)

        api_row = ttk.Frame(api_frame)
        api_row.pack(fill="x", pady=2)
        ttk.Label(api_row, text="API URL", width=16).pack(side="left")
        ttk.Entry(api_row, textvariable=self.api_url).pack(side="left", fill="x", expand=True)

        model_row = ttk.Frame(api_frame)
        model_row.pack(fill="x", pady=2)
        ttk.Label(model_row, text="モデル", width=16).pack(side="left")
        self.model_combo = ttk.Combobox(model_row, textvariable=self.model, width=42)
        self.model_combo.pack(side="left", fill="x", expand=True)
        ttk.Button(model_row, text="モデル一覧取得", command=self.refresh_models).pack(side="left", padx=(6, 0))

        number_row = ttk.Frame(api_frame)
        number_row.pack(fill="x", pady=2)
        ttk.Label(number_row, text="閾値", width=16).pack(side="left")
        ttk.Entry(number_row, textvariable=self.threshold, width=10).pack(side="left")
        ttk.Label(number_row, text="character閾値").pack(side="left", padx=(16, 4))
        ttk.Entry(number_row, textvariable=self.character_threshold, width=10).pack(side="left")
        ttk.Label(number_row, text="timeout(秒)").pack(side="left", padx=(16, 4))
        ttk.Entry(number_row, textvariable=self.timeout, width=10).pack(side="left")

        tags = ttk.LabelFrame(self, text="タグ調整", padding=8)
        tags.pack(fill="x", pady=6)
        for label, variable in (("先頭に追加", self.additional), ("除外タグ", self.exclude)):
            row = ttk.Frame(tags)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=16).pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)

        options = ttk.Frame(self)
        options.pack(fill="x", pady=4)
        ttk.Checkbutton(options, text="サブフォルダも処理", variable=self.recursive).pack(side="left", padx=4)
        ttk.Checkbutton(options, text="出力TXTを上書き", variable=self.overwrite).pack(side="left", padx=4)
        ttk.Checkbutton(options, text="GIF: 全フレームの信頼度を平均", variable=self.gif_average).pack(side="left", padx=4)
        ttk.Checkbutton(options, text="人物・キャラクター候補だけをタグ付け", variable=self.character_crop).pack(side="left", padx=4)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=4)
        ttk.Button(buttons, text="開始", command=self.start).pack(side="left", padx=4)
        ttk.Button(buttons, text="停止", command=self.stop).pack(side="left", padx=4)
        ttk.Button(buttons, text="ログ消去", command=lambda: self.logbox.delete("1.0", "end")).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)

        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self.logbox.log("PixAI Taggerは1画像につき1行を出力TXTへ保存します。GIFは全フレームのタグ信頼度を平均します。")
        self._refresh_preset_choices()

    def _preset_values(self):
        return {"input_dir": self.input_dir.get(), "output_file": self.output_file.get(), "tagger_kind": self.tagger_kind.get(), "api_url": self.api_url.get(), "model": self.model.get(), "threshold": self.threshold.get(), "character_threshold": self.character_threshold.get(), "timeout": self.timeout.get(), "additional": self.additional.get(), "exclude": self.exclude.get(), "recursive": self.recursive.get(), "overwrite": self.overwrite.get(), "gif_average": self.gif_average.get(), "character_crop": self.character_crop.get()}

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), self._preset_values())
            self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (("input_dir", self.input_dir), ("output_file", self.output_file), ("tagger_kind", self.tagger_kind), ("api_url", self.api_url), ("model", self.model), ("threshold", self.threshold), ("character_threshold", self.character_threshold), ("timeout", self.timeout), ("additional", self.additional), ("exclude", self.exclude), ("recursive", self.recursive), ("overwrite", self.overwrite), ("gif_average", self.gif_average), ("character_crop", self.character_crop)):
                if key in values: variable.set(values[key])
            self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    @staticmethod
    def _split_tags(text):
        return [tag.strip() for tag in text.split(",") if tag.strip()]

    def _apply_tagger_preset(self, _event=None):
        api_url, model = self.TAGGER_PRESETS[self.tagger_kind.get()]
        self.api_url.set(api_url)
        self.model.set(model)

    def start_pixai_api(self):
        _safe_thread(self.logbox, PIXAI_TAGGER_SERVER.start, self.logbox.log)

    def start_taggui(self):
        image_directory = self.input_dir.get().strip()
        if not image_directory:
            self.logbox.log("TagGUIを起動する画像フォルダを指定してください")
            return
        _safe_thread(self.logbox, self.taggui_controller.start, image_directory, self.logbox.log)

    def stop_taggui(self):
        _safe_thread(self.logbox, self.taggui_controller.stop, self.logbox.log)

    def stop_pixai_api(self):
        _safe_thread(self.logbox, PIXAI_TAGGER_SERVER.stop, self.logbox.log)

    def refresh_models(self):
        _safe_thread(self.logbox, self._refresh_models)

    def _refresh_models(self):
        if requests is None:
            raise RuntimeError("requests がインストールされていません")
        api_url = self.api_url.get().strip().rstrip("/")
        if not api_url.endswith("/interrogate"):
            raise ValueError("API URLは /interrogate で終わるURLを指定してください")
        models_url = api_url.rsplit("/", 1)[0] + "/interrogators"
        response = requests.get(models_url, timeout=30)
        response.raise_for_status()
        result = response.json()
        if isinstance(result, dict):
            models = result.get("models", [])
        elif isinstance(result, list):
            models = result
        else:
            models = []
        if not models:
            raise RuntimeError(f"モデル一覧が空です: {result}")

        def update_combo():
            self.model_combo.configure(values=models)
            if self.model.get() not in models:
                self.model.set(models[0])

        self.after(0, update_combo)
        self.logbox.log(f"✅ モデル一覧: {len(models)}件")

    def start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.logbox.log("⚠️ Folder Taggerは実行中です")
            return
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self.run_safe, daemon=True)
        self.worker_thread.start()

    def stop(self):
        self.stop_event.set()
        self.logbox.log("停止要求を送信しました")

    def run_safe(self):
        try:
            self.run()
        except Exception as e:
            self.logbox.log(f"❌ Folder Taggerエラー: {type(e).__name__}: {e}")

    @staticmethod
    def _tag_scores(result):
        def from_value(value):
            if isinstance(value, dict):
                direct = {str(tag).strip(): float(score) for tag, score in value.items() if isinstance(score, (int, float)) and str(tag).strip()}
                if direct: return direct
                for key in ("tag", "tags", "caption"):
                    if key in value:
                        scores = from_value(value[key])
                        if scores: return scores
            if isinstance(value, list):
                scores = {}
                for item in value:
                    if isinstance(item, dict):
                        name = item.get("name", item.get("tag")); score = item.get("confidence", item.get("score", 1.0))
                        if name is not None and isinstance(score, (int, float)): scores[str(name).strip()] = float(score)
                    elif str(item).strip(): scores[str(item).strip()] = 1.0
                if scores: return scores
            if isinstance(value, str): return {tag.strip(): 1.0 for tag in value.split(",") if tag.strip()}
            return {}
        scores = from_value(result)
        if scores: return scores
        return {tag: 1.0 for tag in extract_tagger_tags(result)}

    @staticmethod
    def _average_gif_scores(frame_scores):
        if not frame_scores: return {}
        totals = {}
        for scores in frame_scores:
            for tag, score in scores.items(): totals[tag] = totals.get(tag, 0.0) + float(score)
        return {tag: score / len(frame_scores) for tag, score in totals.items()}

    def _interrogate_bytes(self, data, api_url, model, threshold, character_threshold, timeout):
        encoded = base64.b64encode(data).decode("utf-8")
        if "/tagger/v1/" in api_url:
            payload = {
                "image": encoded,
                "model": model,
                "threshold": threshold,
            }
        else:
            payload = {"image": encoded, "threshold": threshold}
            if "/pixai/v1/" in api_url:
                payload.update({"model": model or PIXAI_TAGGER_MODEL, "character_threshold": character_threshold})
        response = requests.post(api_url, json=payload, timeout=timeout)
        response.raise_for_status()
        return self._tag_scores(response.json())

    def _interrogate(self, image_path, api_url, model, threshold, character_threshold, timeout):
        return self._interrogate_bytes(image_path.read_bytes(), api_url, model, threshold, character_threshold, timeout)

    @staticmethod
    def _crop_character_image(image):
        import cv2
        import numpy as np
        from PIL import Image
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        alpha_min, _ = alpha.getextrema()
        if alpha_min < 255:
            bounds = alpha.getbbox()
            if bounds and (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) >= 16:
                return rgba.crop(bounds).convert("RGB"), "alpha"
        rgb = np.asarray(rgba.convert("RGB"))
        height, width = rgb.shape[:2]
        if min(width, height) < 8:
            return Image.fromarray(rgb), "original"
        margin = max(2, min(width, height) * 8 // 100)
        segmentation = np.zeros((height, width), np.uint8); background = np.zeros((1, 65), np.float64); foreground = np.zeros((1, 65), np.float64)
        try:
            cv2.grabCut(rgb, segmentation, (margin, margin, width - margin * 2, height - margin * 2), background, foreground, 2, cv2.GC_INIT_WITH_RECT)
            mask = np.where((segmentation == 1) | (segmentation == 3), 255, 0).astype("uint8")
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                x, y, crop_width, crop_height = cv2.boundingRect(max(contours, key=cv2.contourArea))
                if crop_width * crop_height < width * height * 0.95:
                    padding = max(2, min(width, height) // 40)
                    return Image.fromarray(rgb).crop((max(0, x-padding), max(0, y-padding), min(width, x+crop_width+padding), min(height, y+crop_height+padding))), "grabcut"
        except cv2.error:
            pass
        return Image.fromarray(rgb), "original"

    def _interrogate_pil_image(self, image, api_url, model, threshold, character_threshold, timeout, character_crop):
        if character_crop:
            image, _ = self._crop_character_image(image)
        buffer = io.BytesIO(); image.convert("RGB").save(buffer, format="PNG")
        return self._interrogate_bytes(buffer.getvalue(), api_url, model, threshold, character_threshold, timeout)

    def _interrogate_gif(self, image_path, api_url, model, threshold, character_threshold, timeout, character_crop=False):
        from PIL import Image, ImageSequence
        frame_scores = []
        with Image.open(image_path) as image:
            for frame in ImageSequence.Iterator(image):
                if self.stop_event.is_set(): break
                frame_scores.append(self._interrogate_pil_image(frame, api_url, model, threshold, character_threshold, timeout, character_crop))
        if not frame_scores: raise RuntimeError("GIFから処理可能なフレームを取得できませんでした")
        return self._average_gif_scores(frame_scores), len(frame_scores)

    def run(self):
        if requests is None:
            raise RuntimeError("requests がインストールされていません")
        root = Path(self.input_dir.get().strip())
        if not root.is_dir():
            raise FileNotFoundError(f"画像フォルダがありません: {root}")
        output_text = self.output_file.get().strip()
        if not output_text:
            raise ValueError("出力TXTを指定してください")
        output = Path(output_text)
        if output.exists() and not self.overwrite.get():
            raise FileExistsError(f"出力TXTが既にあります: {output}")

        api_url = self.api_url.get().strip().rstrip("/")
        if not api_url:
            raise ValueError("API URLを指定してください")
        model = self.model.get().strip()
        if "/tagger/v1/" in api_url and not model:
            raise ValueError("専用Tagger APIではモデル指定が必要です")
        threshold = float(self.threshold.get())
        if not 0 <= threshold <= 1:
            raise ValueError("閾値は0から1で指定してください")
        character_threshold = float(self.character_threshold.get())
        if not 0 <= character_threshold <= 1:
            raise ValueError("character閾値は0から1で指定してください")
        timeout = int(self.timeout.get())
        if timeout <= 0:
            raise ValueError("timeoutは1秒以上にしてください")

        iterator = root.rglob("*") if self.recursive.get() else root.iterdir()
        images = sorted(
            path for path in iterator
            if path.is_file() and path.suffix.lower() in self.IMAGE_EXTENSIONS
        )
        if not images:
            raise FileNotFoundError(f"画像が見つかりません: {root}")

        additional = self._split_tags(self.additional.get())
        exclude_raw = self._split_tags(self.exclude.get())
        excluded = set(exclude_raw)
        excluded.update(tag.replace(" ", "_") for tag in exclude_raw)
        output.parent.mkdir(parents=True, exist_ok=True)
        completed = 0
        errors = 0
        self.logbox.log(f"▶️ Folder Tagger開始: {len(images)}画像")

        with output.open("w", encoding="utf-8", newline="\n") as destination:
            for index, image_path in enumerate(images, start=1):
                if self.stop_event.is_set():
                    break
                self.logbox.log(f"[{index}/{len(images)}] {image_path}")
                try:
                    if image_path.suffix.lower() == ".gif" and self.gif_average.get():
                        scores, frame_count = self._interrogate_gif(image_path, api_url, model, threshold, character_threshold, timeout, self.character_crop.get())
                        self.logbox.log(f"  GIF {frame_count}フレームを平均")
                    elif self.character_crop.get():
                        from PIL import Image
                        with Image.open(image_path) as image:
                            cropped, crop_source = self._crop_character_image(image)
                            scores = self._interrogate_pil_image(cropped, api_url, model, threshold, character_threshold, timeout, False)
                        self.logbox.log(f"  キャラクター候補を切り出し: {crop_source}")
                    else:
                        scores = self._interrogate(image_path, api_url, model, threshold, character_threshold, timeout)
                    tags = [tag for tag, score in scores.items() if score >= threshold]
                    tags = [
                        tag for tag in tags
                        if tag not in excluded and tag.replace(" ", "_") not in excluded
                    ]
                    destination.write(", ".join(additional + tags) + "\n")
                    destination.flush()
                    completed += 1
                    self.logbox.log(f"  ✅ {len(additional) + len(tags)}タグ")
                except Exception as e:
                    errors += 1
                    destination.write(f"ERROR: {type(e).__name__}: {e}\n")
                    destination.flush()
                    self.logbox.log(f"  ❌ {type(e).__name__}: {e}")

        if self.stop_event.is_set():
            self.logbox.log(f"⏹️ 停止: 成功{completed}／エラー{errors}／全{len(images)}")
        else:
            self.logbox.log(f"✅ 完了: 成功{completed}／エラー{errors}／出力 {output}")
