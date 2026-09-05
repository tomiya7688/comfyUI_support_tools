from ..context import *
from ..context import _safe_thread
from ..services import LogBox, LabeledPathRow
from ..backend.process_cpu_limiter import ProcessCpuLimiter
from ..backend.touka_dataset_preset_builder import ToukaDatasetPresetBuilder
from ..backend.touka_evaluator import ToukaEvaluator
from ..widgets.preset_store import PresetStore
from ..widgets.responsive_button_row import ResponsiveButtonRow
import json

TOUKA_SETTINGS_FILE = USER_INPUT_DIR / "config" / "touka" / "settings.json"

OBJECT_PRESET_LABELS = {
    "汎用": "generic", "服・衣類": "clothing", "布・タオル": "cloth",
    "シャツ・ブラウス": "shirt", "ブラジャー": "bra", "ショーツ・パンツ": "panties", "肌（輪郭優先）": "skin", "カーペット・ラグ": "carpet",
    "リボン・紐": "ribbon", "規則物体": "regular", "塊状物体": "solid",
}
TRANSPARENT_TARGET_PRESET_LABELS = {
    "自動推定": "auto", "薄い布": "thin_cloth", "Tシャツ": "t_shirt", "厚い布・毛布": "thick_cloth",
    "薄紙": "thin_paper", "透明フィルム": "clear_film",
}

class ToukaEnhancerTab(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=10); self.process = None; self.ranking_data = {}
        self.preset_store = PresetStore("touka"); self.preset_name = tk.StringVar()
        self.mode = tk.StringVar(value="image"); self.profile = tk.StringVar(value="balanced"); self.object_preset = tk.StringVar(value="汎用"); self.surface_preset = tk.StringVar(value="自動推定"); self.cpu_cores = tk.StringVar(); self.preview_seconds = tk.StringVar(value="5"); self.preview_start_seconds = tk.StringVar(value="0"); self.roi = tk.StringVar(); self.input_path = tk.StringVar(); self.output_path = tk.StringVar(); self.reference_path = tk.StringVar(); self.surface_reference_path = tk.StringVar(); self.evaluation_path = tk.StringVar(); self.dataset_preset_name = tk.StringVar(); self.denoise_references = tk.BooleanVar(value=False); self._restore_settings(); self._build()

    def _restore_settings(self):
        try:
            values = json.loads(TOUKA_SETTINGS_FILE.read_text(encoding="utf-8"))
            if not isinstance(values, dict): return
        except (OSError, ValueError):
            return
        for key, variable in (("mode", self.mode), ("profile", self.profile), ("object_preset", self.object_preset), ("surface_preset", self.surface_preset), ("cpu_cores", self.cpu_cores), ("preview_seconds", self.preview_seconds), ("preview_start_seconds", self.preview_start_seconds), ("roi", self.roi), ("input_path", self.input_path), ("output_path", self.output_path), ("reference_path", self.reference_path), ("surface_reference_path", self.surface_reference_path), ("evaluation_path", self.evaluation_path), ("dataset_preset_name", self.dataset_preset_name), ("denoise_references", self.denoise_references)):
            value = values.get(key)
            if isinstance(value, (str, bool)): variable.set(value)

    def save_settings(self):
        values = {"mode": self.mode.get(), "profile": self.profile.get(), "object_preset": self.object_preset.get(), "surface_preset": self.surface_preset.get(), "cpu_cores": self.cpu_cores.get(), "preview_seconds": self.preview_seconds.get(), "preview_start_seconds": self.preview_start_seconds.get(), "roi": self.roi.get(), "input_path": self.input_path.get(), "output_path": self.output_path.get(), "reference_path": self.reference_path.get(), "surface_reference_path": self.surface_reference_path.get(), "evaluation_path": self.evaluation_path.get(), "dataset_preset_name": self.dataset_preset_name.get(), "denoise_references": self.denoise_references.get()}
        try:
            TOUKA_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOUKA_SETTINGS_FILE.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.logbox.log(f"設定を保存しました: {TOUKA_SETTINGS_FILE}")
        except OSError as exc:
            self.logbox.log(f"設定保存エラー: {exc}")

    def _preset_values(self):
        return {"mode": self.mode.get(), "profile": self.profile.get(), "object_preset": self.object_preset.get(), "surface_preset": self.surface_preset.get(), "cpu_cores": self.cpu_cores.get(), "preview_seconds": self.preview_seconds.get(), "preview_start_seconds": self.preview_start_seconds.get(), "roi": self.roi.get(), "input_path": self.input_path.get(), "output_path": self.output_path.get(), "reference_path": self.reference_path.get(), "surface_reference_path": self.surface_reference_path.get(), "evaluation_path": self.evaluation_path.get(), "dataset_preset_name": self.dataset_preset_name.get(), "denoise_references": self.denoise_references.get()}

    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), self._preset_values()); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (("mode", self.mode), ("profile", self.profile), ("object_preset", self.object_preset), ("surface_preset", self.surface_preset), ("cpu_cores", self.cpu_cores), ("preview_seconds", self.preview_seconds), ("preview_start_seconds", self.preview_start_seconds), ("roi", self.roi), ("input_path", self.input_path), ("output_path", self.output_path), ("reference_path", self.reference_path), ("surface_reference_path", self.surface_reference_path), ("evaluation_path", self.evaluation_path), ("dataset_preset_name", self.dataset_preset_name), ("denoise_references", self.denoise_references)):
                if key in values: variable.set(values[key])
            self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    def _build(self):
        ttk.Label(self, text="元データに残る色差・明暗差・輪郭を強調します。完全に隠れた情報は復元できません。").pack(anchor="w", pady=(0, 8))
        mode_row = ttk.Frame(self); mode_row.pack(fill="x", pady=3); ttk.Label(mode_row, text="モード", width=16).pack(side="left")
        ttk.Combobox(mode_row, textvariable=self.mode, values=("image", "video"), state="readonly", width=12).pack(side="left")
        ttk.Label(mode_row, text="候補").pack(side="left", padx=(20,4)); ttk.Combobox(mode_row, textvariable=self.profile, values=("color", "color_strong", "shape", "shape_strong", "balanced", "balanced_strong", "conservative", "observed_color", "observed_conservative", "all"), state="readonly", width=20).pack(side="left")
        range_row = ttk.Frame(self); range_row.pack(fill="x", pady=3); ttk.Label(range_row, text="開始秒", width=16).pack(side="left"); ttk.Entry(range_row, textvariable=self.preview_start_seconds, width=6).pack(side="left"); ttk.Label(range_row, text="プレビュー秒").pack(side="left", padx=(8,4)); ttk.Entry(range_row, textvariable=self.preview_seconds, width=6).pack(side="left"); ttk.Label(range_row, text="（長さ0=全尺）").pack(side="left")
        target_row = ttk.Frame(self); target_row.pack(fill="x", pady=3); ttk.Label(target_row, text="強調対象", width=16).pack(side="left"); ttk.Combobox(target_row, textvariable=self.object_preset, values=tuple(OBJECT_PRESET_LABELS), state="readonly", width=16).pack(side="left"); ttk.Label(target_row, text="透過対象").pack(side="left", padx=(20,4)); ttk.Combobox(target_row, textvariable=self.surface_preset, values=tuple(TRANSPARENT_TARGET_PRESET_LABELS), state="readonly", width=16).pack(side="left")
        self._path_row("入力フォルダ/動画", self.input_path, False)
        self._path_row("出力フォルダ/動画", self.output_path, True)
        self._path_row("評価履歴フォルダ", self.evaluation_path, False)
        reference_row = ttk.Frame(self); reference_row.pack(fill="x", pady=3); ttk.Label(reference_row, text="強調対象参考画像", width=16).pack(side="left"); ttk.Entry(reference_row, textvariable=self.reference_path).pack(side="left", fill="x", expand=True); ttk.Button(reference_row, text="フォルダ", command=lambda: self._choose_directory(self.reference_path, False)).pack(side="left", padx=4); ttk.Button(reference_row, text="強調対象を提案", command=self.suggest_reference_preset).pack(side="left", padx=4)
        ttk.Checkbutton(self, text="参考画像のノイズを抑えてから形状・表面色を推定", variable=self.denoise_references).pack(anchor="w", pady=2)
        dataset_preset_row = ttk.Frame(self); dataset_preset_row.pack(fill="x", pady=3); ttk.Label(dataset_preset_row, text="データセットプリセット名", width=16).pack(side="left"); ttk.Entry(dataset_preset_row, textvariable=self.dataset_preset_name, width=32).pack(side="left"); ttk.Button(dataset_preset_row, text="参考画像から作成", command=self.create_dataset_preset).pack(side="left", padx=4)
        surface_row = ttk.Frame(self); surface_row.pack(fill="x", pady=3); ttk.Label(surface_row, text="透過対象参考画像", width=16).pack(side="left"); ttk.Entry(surface_row, textvariable=self.surface_reference_path).pack(side="left", fill="x", expand=True); ttk.Button(surface_row, text="フォルダ", command=lambda: self._choose_directory(self.surface_reference_path, False)).pack(side="left", padx=4)
        cpu_row = ttk.Frame(self); cpu_row.pack(fill="x", pady=3); ttk.Label(cpu_row, text="使用CPU論理数", width=16).pack(side="left"); ttk.Entry(cpu_row, textvariable=self.cpu_cores, width=8).pack(side="left"); ttk.Label(cpu_row, text="空欄なら制限なし").pack(side="left", padx=6)
        action_row = ResponsiveButtonRow(self); action_row.pack(fill="x", pady=(8, 3))
        for text, command in (("処理開始", self.start), ("停止", self.stop), ("環境診断", self.diagnose_environment), ("Fashionpediaプリセットを作成", self.create_fashionpedia_presets), ("設定を保存", self.save_settings)):
            action_row.add(ttk.Button(action_row, text=text, command=command))
        action_row.add(ttk.Label(action_row, text="preset")); self.preset_combo = ttk.Combobox(action_row, textvariable=self.preset_name, width=16); action_row.add(self.preset_combo); action_row.add(ttk.Button(action_row, text="保存", command=self.save_preset)); action_row.add(ttk.Button(action_row, text="読込", command=self.load_preset))
        selection_row = ResponsiveButtonRow(self); selection_row.pack(fill="x", pady=3)
        for text, command in (("画像を開いて範囲/Auto object選択", self.open_editor), ("動画対象を選択", self.select_video_roi), ("動画: Auto object", self.auto_select_video_object), ("プレビュー範囲を選択", self.select_preview_range), ("代表区間を自動選択", self.auto_select_preview_range)):
            selection_row.add(ttk.Button(selection_row, text=text, command=command))
        result_row = ResponsiveButtonRow(self); result_row.pack(fill="x", pady=(3, 8))
        for text, command in (("ランキングJSONを開く", self.open_scores), ("候補比較画像を開く", self.open_comparison), ("ランキング読込", self.load_ranking), ("選択候補を開く", self.open_selected_candidate), ("選択候補のマスクを開く", self.open_selected_mask), ("選択候補の診断", self.show_selected_diagnostics), ("選択候補を全尺レンダリング", self.render_selected_candidate)):
            result_row.add(ttk.Button(result_row, text=text, command=command))
        self.ranking = ttk.Treeview(self, columns=("rank", "profile", "score", "stability", "tracking", "file", "mask"), show="headings", height=6)
        for key, title, width in (("rank", "順位", 50), ("profile", "候補", 100), ("score", "score", 80), ("stability", "時間安定", 80), ("tracking", "追跡", 60), ("file", "出力", 400), ("mask", "マスク", 320)):
            self.ranking.heading(key, text=title); self.ranking.column(key, width=width, anchor="w")
        self.ranking.pack(fill="x", pady=(0, 6))
        self.logbox = LogBox(self); self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    def open_editor(self):
        python = NUNO_TOUKA_DIR / ".venv" / "Scripts" / "python.exe"
        if not python.is_file(): python = Path(sys.executable)
        try:
            subprocess.Popen([str(python), str(NUNO_TOUKA_DIR / "image_enhancer.py")], cwd=str(NUNO_TOUKA_DIR))
            self.logbox.log("画像編集画面を起動しました。Auto objectはその画面上部にあります。")
        except Exception as exc: self.logbox.log(f"起動エラー: {exc}")

    def diagnose_environment(self):
        interpreters = [("Tabbed GUI", Path(sys.executable)), ("Touka専用", NUNO_TOUKA_DIR / ".venv" / "Scripts" / "python.exe")]
        for label, python in interpreters:
            if not python.is_file():
                self.logbox.log(f"{label}: Pythonが見つかりません: {python}")
                continue
            result = subprocess.run([str(python), "-c", "import cv2, numpy, PIL; print('cv2=' + cv2.__version__ + ' numpy=' + numpy.__version__ + ' Pillow=' + PIL.__version__)"], capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode == 0:
                self.logbox.log(f"{label}: OK / {result.stdout.strip()}")
            else:
                self.logbox.log(f"{label}: 依存不足 / {result.stderr.strip() or result.stdout.strip()}")

    def create_fashionpedia_presets(self):
        python = NUNO_TOUKA_DIR / ".venv" / "Scripts" / "python.exe"
        if not python.is_file(): python = Path(sys.executable)
        command = [str(python), str(NUNO_TOUKA_DIR / "fashionpedia_preset_builder.py")]
        self.logbox.log("FashionpediaからToukaプリセットを作成します")
        _safe_thread(self.logbox, self._run_fashionpedia_preset_builder, command)

    def _run_fashionpedia_preset_builder(self, command):
        result = subprocess.run(command, cwd=str(NUNO_TOUKA_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        message = result.stdout.strip() or result.stderr.strip()
        if result.returncode != 0:
            self.after(0, lambda: self.logbox.log(f"Fashionpediaプリセット作成エラー: {message}"))
            return
        self.after(0, lambda: self._finish_fashionpedia_preset_builder(message))

    def _finish_fashionpedia_preset_builder(self, message):
        self._refresh_preset_choices()
        self.logbox.log(f"Fashionpediaプリセットを作成しました\n{message}")

    def create_dataset_preset(self):
        try:
            builder = ToukaDatasetPresetBuilder()
            values = builder.values(self.reference_path.get().strip(), self.object_preset.get())
            path = self.preset_store.save(self.dataset_preset_name.get(), values)
            self.dataset_preset_name.set(path.stem); self._refresh_preset_choices()
            self.logbox.log(f"データセットプリセットを作成しました: {path} / 参考画像 {builder.image_count(self.reference_path.get().strip())} 件")
        except Exception as error:
            self.logbox.log(f"データセットプリセット作成エラー: {error}")

    def suggest_reference_preset(self):
        reference_dir = Path(self.reference_path.get().strip())
        if not reference_dir.is_dir():
            self.logbox.log(f"強調対象参考画像フォルダが見つかりません: {reference_dir}")
            return
        python = NUNO_TOUKA_DIR / ".venv" / "Scripts" / "python.exe"
        if not python.is_file():
            python = Path(sys.executable)
        command = [str(python), str(NUNO_TOUKA_DIR / "touka_batch.py"), "--analyze-reference", "--reference-dir", str(reference_dir)]
        if self.denoise_references.get(): command.append("--denoise-reference")
        _safe_thread(self.logbox, self._read_reference_suggestion, command)

    def _read_reference_suggestion(self, command):
        result = subprocess.run(command, cwd=str(NUNO_TOUKA_DIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            self.after(0, lambda: self.logbox.log(f"強調対象の提案エラー: {result.stderr.strip() or result.stdout.strip()}"))
            return
        try:
            suggestion = json.loads(result.stdout)
            preset = suggestion["preset"]
            image_count = int(suggestion["image_count"])
            confidence = float(suggestion.get("confidence", 0.0))
            common_count = int(suggestion.get("common_object_count", image_count))
            shape_consistency = float(suggestion.get("common_shape_consistency", 0.0))
            outlier_count = int(suggestion.get("outlier_count", 0))
            distribution = suggestion.get("distribution", {})
            if not isinstance(distribution, dict):
                raise TypeError("形状内訳が不正です")
            label = next(label for label, value in OBJECT_PRESET_LABELS.items() if value == preset)
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
            self.after(0, lambda: self.logbox.log(f"強調対象の提案解析エラー: {error}"))
            return
        self.after(0, lambda: self._apply_reference_suggestion(label, image_count, confidence, distribution, common_count, shape_consistency, outlier_count))

    def _apply_reference_suggestion(self, label, image_count, confidence, distribution, common_count=0, shape_consistency=0.0, outlier_count=0):
        self.object_preset.set(label)
        details = ", ".join(f"{key}: {value}" for key, value in distribution.items()) or "有効な形状なし"
        self.logbox.log(f"強調対象参考画像から提案: {label}（解析画像 {image_count} 件、共通候補 {common_count} 件、形状一致 {shape_consistency:.0%}、除外候補 {outlier_count} 件、確信度 {confidence:.0%}、内訳 {details}）")

    def select_video_roi(self):
        try:
            import cv2
            from PIL import Image, ImageTk
            source = Path(self.input_path.get())
            video = source if source.is_file() else next((path for path in source.rglob("*") if path.suffix.lower() in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}), None)
            if video is None: raise ValueError("入力動画が見つかりません")
            capture = cv2.VideoCapture(str(video)); ok, frame = capture.read(); capture.release()
            if not ok: raise ValueError(f"動画を読めません: {video}")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); original_h, original_w = rgb.shape[:2]
            image = Image.fromarray(rgb); image.thumbnail((900, 600)); preview_w, preview_h = image.size
            dialog = tk.Toplevel(self); dialog.title("対象範囲をドラッグして選択"); canvas = tk.Canvas(dialog, width=preview_w, height=preview_h); canvas.pack(); photo = ImageTk.PhotoImage(image); canvas.create_image(0, 0, anchor="nw", image=photo); canvas.image = photo
            state = {"start": None, "item": None}
            def press(event): state["start"] = (event.x, event.y)
            def drag(event):
                if state["start"]:
                    if state["item"]: canvas.delete(state["item"])
                    state["item"] = canvas.create_rectangle(*state["start"], event.x, event.y, outline="#00ffff", width=2)
            def release(event):
                if not state["start"]: return
                x0,y0=state["start"]; x1,y1=event.x,event.y; state["start"]=None
                left, right = sorted((max(0, min(preview_w, x0)), max(0, min(preview_w, x1))))
                top, bottom = sorted((max(0, min(preview_h, y0)), max(0, min(preview_h, y1))))
                if right-left<4 or bottom-top<4: return
                self.roi.set(f"{left/preview_w:.6f},{top/preview_h:.6f},{(right-left)/preview_w:.6f},{(bottom-top)/preview_h:.6f}")
                self.logbox.log(f"動画対象範囲を設定: {self.roi.get()}"); dialog.destroy()
            canvas.bind("<ButtonPress-1>", press); canvas.bind("<B1-Motion>", drag); canvas.bind("<ButtonRelease-1>", release)
        except Exception as exc: self.logbox.log(f"動画対象選択エラー: {exc}")

    def auto_select_video_object(self):
        try:
            import cv2
            import numpy as np
            from PIL import Image, ImageTk
            source = Path(self.input_path.get())
            video = source if source.is_file() else next((path for path in source.rglob("*") if path.suffix.lower() in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}), None)
            if video is None: raise ValueError("入力動画が見つかりません")
            capture = cv2.VideoCapture(str(video)); ok, frame = capture.read(); capture.release()
            if not ok: raise ValueError(f"動画を読めません: {video}")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB); height, width = rgb.shape[:2]
            margin = max(2, min(width, height) * 8 // 100)
            segmentation = np.zeros((height, width), np.uint8); background = np.zeros((1, 65), np.float64); foreground = np.zeros((1, 65), np.float64)
            cv2.grabCut(rgb, segmentation, (margin, margin, width - margin * 2, height - margin * 2), background, foreground, 2, cv2.GC_INIT_WITH_RECT)
            mask = np.where((segmentation == 1) | (segmentation == 3), 255, 0).astype("uint8")
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours: raise ValueError("自動対象を検出できませんでした。動画対象を選択で範囲を指定してください")
            x, y, object_width, object_height = cv2.boundingRect(max(contours, key=cv2.contourArea))
            padding = max(2, min(width, height) // 50); left=max(0, x-padding); top=max(0, y-padding); right=min(width, x+object_width+padding); bottom=min(height, y+object_height+padding)
            aspect=max(right-left, bottom-top) / max(1, min(right-left, bottom-top)); area=cv2.contourArea(max(contours, key=cv2.contourArea)) / max(1, width*height)
            preset = "ribbon" if aspect >= 3.0 else "solid" if area >= 0.45 else "cloth" if aspect <= 1.8 else "regular"
            label = next(label for label, value in OBJECT_PRESET_LABELS.items() if value == preset)
            self.roi.set(f"{left/width:.6f},{top/height:.6f},{(right-left)/width:.6f},{(bottom-top)/height:.6f}"); self.object_preset.set(label)
            preview = rgb.copy(); preview[mask == 0] = (preview[mask == 0] * 0.22).astype("uint8"); cv2.rectangle(preview, (left, top), (right, bottom), (0, 255, 255), 2)
            image = Image.fromarray(preview); image.thumbnail((900, 600)); dialog=tk.Toplevel(self); dialog.title("Auto object 結果"); photo=ImageTk.PhotoImage(image); canvas=tk.Canvas(dialog, width=image.width, height=image.height); canvas.pack(); canvas.create_image(0, 0, anchor="nw", image=photo); canvas.image=photo
            ttk.Label(dialog, text=f"対象: {label}  ROI: {self.roi.get()}").pack(padx=8, pady=8)
            self.logbox.log(f"Auto object: {label} / ROI={self.roi.get()}")
        except Exception as exc: self.logbox.log(f"動画Auto objectエラー: {exc}")

    def select_preview_range(self):
        try:
            import cv2
            source = Path(self.input_path.get())
            video = source if source.is_file() else next((path for path in source.rglob("*") if path.suffix.lower() in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}), None)
            if video is None: raise ValueError("入力動画が見つかりません")
            capture = cv2.VideoCapture(str(video)); fps = capture.get(cv2.CAP_PROP_FPS) or 30.0; frames = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0; capture.release()
            duration = max(1.0, frames / fps)
            dialog = tk.Toplevel(self); dialog.title("候補プレビュー範囲"); dialog.transient(self.winfo_toplevel())
            ttk.Label(dialog, text=f"{video.name}  /  {duration:.1f} 秒").pack(padx=12, pady=(12, 6))
            start = tk.DoubleVar(value=min(float(self.preview_start_seconds.get() or 0), duration)); length = tk.DoubleVar(value=min(max(0.5, float(self.preview_seconds.get() or 5)), duration))
            ttk.Label(dialog, text="開始秒").pack(anchor="w", padx=12); ttk.Scale(dialog, from_=0, to=max(0, duration - 0.1), variable=start, orient="horizontal", length=420).pack(padx=12)
            ttk.Label(dialog, text="候補の長さ（秒）").pack(anchor="w", padx=12); ttk.Scale(dialog, from_=0.5, to=min(30.0, duration), variable=length, orient="horizontal", length=420).pack(padx=12)
            def apply_range():
                selected_start = min(start.get(), max(0, duration - 0.1)); selected_length = min(length.get(), max(0.1, duration - selected_start))
                self.preview_start_seconds.set(f"{selected_start:.2f}"); self.preview_seconds.set(f"{selected_length:.2f}"); self.logbox.log(f"プレビュー範囲: {selected_start:.2f}秒 から {selected_length:.2f}秒"); dialog.destroy()
            ttk.Button(dialog, text="この範囲を使う", command=apply_range).pack(pady=12)
        except Exception as exc: self.logbox.log(f"プレビュー範囲選択エラー: {exc}")

    def auto_select_preview_range(self):
        try:
            import cv2
            import numpy as np
            source = Path(self.input_path.get())
            video = source if source.is_file() else next((path for path in source.rglob("*") if path.suffix.lower() in {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}), None)
            if video is None: raise ValueError("入力動画が見つかりません")
            capture = cv2.VideoCapture(str(video)); fps = capture.get(cv2.CAP_PROP_FPS) or 30.0; total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total_frames < 1: raise ValueError(f"動画を読めません: {video}")
            roi = None
            if self.roi.get().strip():
                values = tuple(float(value) for value in self.roi.get().split(","))
                if len(values) == 4: roi = values
            best_frame = 0; best_score = float("-inf"); previous = None; step = max(1, int(fps))
            for frame_index in range(0, total_frames, step):
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index); ok, frame = capture.read()
                if not ok: continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                if roi:
                    height, width = gray.shape; x=int(roi[0]*width); y=int(roi[1]*height); right=min(width, x+max(2,int(roi[2]*width))); bottom=min(height, y+max(2,int(roi[3]*height))); gray=gray[y:bottom, x:right]
                if gray.size < 16: continue
                detail = float(cv2.Laplacian(gray, cv2.CV_32F).var())
                motion = 0.0 if previous is None or previous.shape != gray.shape else float(np.mean(np.abs(gray.astype(np.float32) - previous.astype(np.float32))))
                score = min(detail, 2000.0) * 0.02 + motion * 1.5
                if score > best_score: best_score = score; best_frame = frame_index
                previous = gray
            capture.release()
            duration = total_frames / fps; length = min(5.0, duration); center = best_frame / fps; start = min(max(0.0, center - length / 2), max(0.0, duration - length))
            self.preview_start_seconds.set(f"{start:.2f}"); self.preview_seconds.set(f"{length:.2f}")
            self.logbox.log(f"代表区間を設定: {start:.2f}秒から {length:.2f}秒（解析score={best_score:.2f}）")
        except Exception as exc: self.logbox.log(f"代表区間の自動選択エラー: {exc}")

    def open_scores(self):
        path = Path(self.output_path.get()) / ("candidate_ranking.json" if self.profile.get() == "all" else "candidate_scores.json")
        if not path.is_file(): self.logbox.log(f"ランキングJSONがありません: {path}"); return
        try: os.startfile(str(path))
        except Exception as exc: self.logbox.log(f"ランキング表示エラー: {exc}")

    def open_comparison(self):
        path = Path(self.output_path.get()) / "candidate_comparison.png"
        if not path.is_file():
            self.logbox.log(f"候補比較画像がありません（候補全生成後に作られます）: {path}"); return
        try: os.startfile(path)
        except Exception as exc: self.logbox.log(f"候補比較画像を開けません: {exc}")

    def load_ranking(self):
        path = Path(self.output_path.get()) / ("candidate_ranking.json" if self.profile.get() == "all" else "candidate_scores.json")
        if not path.is_file(): self.logbox.log(f"ランキングJSONがありません: {path}"); return
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            for item in self.ranking.get_children(): self.ranking.delete(item)
            self.ranking_data = {}
            for index, item in enumerate(rows, 1):
                row_id = self.ranking.insert("", "end", values=(index, item.get("profile", self.profile.get()), f"{item.get('score', 0):.2f}", f"{item.get('temporal_shape_consistency', 0):.3f}", f"{item.get('tracking_confidence', 0):.2f}", item.get("output", ""), item.get("mask_preview", "")))
                self.ranking_data[row_id] = item
            self.logbox.log(f"ランキングを読み込みました: {len(rows)}件")
        except Exception as exc: self.logbox.log(f"ランキング読込エラー: {exc}")

    def open_selected_candidate(self):
        selection = self.ranking.selection()
        if not selection: self.logbox.log("ランキングから候補を選択してください"); return
        path = self.ranking.item(selection[0], "values")[5]
        if not Path(path).is_file(): self.logbox.log(f"候補動画が見つかりません: {path}"); return
        try: os.startfile(path)
        except Exception as exc: self.logbox.log(f"候補動画を開けません: {exc}")

    def open_selected_mask(self):
        selection = self.ranking.selection()
        if not selection:
            self.logbox.log("ランキングから候補を選択してください"); return
        path = self.ranking.item(selection[0], "values")[6]
        if not Path(path).is_file():
            self.logbox.log(f"マスクプレビューが見つかりません: {path}"); return
        try: os.startfile(path)
        except Exception as exc: self.logbox.log(f"マスクプレビューを開けません: {exc}")

    def show_selected_diagnostics(self):
        selection = self.ranking.selection()
        if not selection:
            self.logbox.log("ランキングから候補を選択してください"); return
        item = self.ranking_data.get(selection[0])
        if item is None:
            self.logbox.log("ランキングを読み込み直してください"); return
        fields = (
            ("score", "総合スコア"), ("profile", "候補"), ("object_preset", "強調対象プリセット"), ("surface_preset", "透過対象プリセット"), ("reference_preset", "強調対象参考画像の形状ヒント"), ("reference_image_count", "強調対象参考画像数"), ("surface_reference_dir", "透過対象参考画像"), ("surface_reference_image_count", "透過対象参考画像数"), ("surface_reference_clusters", "透過対象の色クラスタ"),
            ("tracking_confidence", "追跡信頼度"), ("target_motion", "対象移動量"), ("camera_motion", "カメラ移動量"),
            ("temporal_shape_consistency", "形状の時間安定"), ("temporal_fusion_frames", "時間融合フレーム数"), ("temporal_fusion_strength", "時間融合の平均強度"), ("observed_color_frames", "観測色蓄積フレーム数"),
            ("flicker", "フリッカー"), ("noise", "ノイズ増加"), ("halo", "ハロー"), ("clipping", "白飛び・黒潰れ"),
            ("scene_change_count", "シーン切替"), ("mask_reinitialize_count", "マスク再初期化"), ("track_reacquire_count", "追跡再取得"),
        )
        lines = ["候補診断", ""]
        for key, label in fields:
            value = item.get(key, "-")
            lines.append(f"{label}: {value:.4f}" if isinstance(value, float) else f"{label}: {value}")
        dialog = tk.Toplevel(self); dialog.title("候補診断")
        text = tk.Text(dialog, width=54, height=len(lines) + 2, wrap="word")
        text.insert("1.0", "\n".join(lines)); text.configure(state="disabled"); text.pack(padx=12, pady=12)

    def render_selected_candidate(self):
        selection = self.ranking.selection()
        if not selection:
            self.logbox.log("ランキングから候補を選択してください"); return
        profile = self.ranking.item(selection[0], "values")[1]
        if profile not in {"color", "color_strong", "shape", "shape_strong", "balanced", "balanced_strong", "conservative", "observed_color", "observed_conservative"}:
            self.logbox.log(f"全尺レンダリングできない候補です: {profile}"); return
        self.profile.set(profile); self.preview_start_seconds.set("0"); self.preview_seconds.set("0")
        self.logbox.log(f"全尺レンダリング開始: {profile}")
        self.start()

    def _path_row(self, label, variable, output):
        row = ttk.Frame(self); row.pack(fill="x", pady=3); ttk.Label(row, text=label, width=16).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="フォルダ", command=lambda: self._choose_directory(variable, output)).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="ファイル", command=lambda: self._choose_file(variable, output)).pack(side="left", padx=4)

    def _choose_directory(self, variable, output):
        value = filedialog.askdirectory(title="入力フォルダを選択" if not output else "出力フォルダを選択")
        if value: variable.set(value)

    def _choose_file(self, variable, output):
        video_types = [("動画", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("すべて", "*.*")]
        image_types = [("画像", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"), ("すべて", "*.*")]
        if output:
            value = filedialog.asksaveasfilename(title="出力動画ファイルを指定", defaultextension=".mp4", filetypes=video_types)
        else:
            value = filedialog.askopenfilename(title="入力ファイルを選択", filetypes=video_types if self.mode.get() == "video" else image_types)
        if value: variable.set(value)

    def start(self):
        if self.process and self.process.poll() is None: self.logbox.log("処理中です"); return
        source, target = Path(self.input_path.get()), Path(self.output_path.get())
        if not source.exists(): self.logbox.log(f"入力が見つかりません: {source}"); return
        if not self.output_path.get().strip(): self.logbox.log("出力先を指定してください"); return
        try:
            preview_start = float(self.preview_start_seconds.get().strip() or "0")
            preview_seconds = float(self.preview_seconds.get().strip() or "0")
        except ValueError:
            self.logbox.log("開始秒・プレビュー秒には数値を入力してください"); return
        if preview_start < 0 or preview_seconds < 0:
            self.logbox.log("開始秒・プレビュー秒は0以上で指定してください"); return
        if self.profile.get() == "all" and target.suffix:
            self.logbox.log("候補全生成（all）の出力先はフォルダを指定してください"); return
        if self.mode.get() == "video" and source.is_dir() and target.suffix:
            self.logbox.log("入力がフォルダの場合、出力先もフォルダを指定してください"); return
        if self.reference_path.get().strip() and not Path(self.reference_path.get()).is_dir():
            self.logbox.log(f"強調対象参考画像フォルダが見つかりません: {self.reference_path.get()}"); return
        if self.surface_reference_path.get().strip() and not Path(self.surface_reference_path.get()).is_dir():
            self.logbox.log(f"透過対象参考画像フォルダが見つかりません: {self.surface_reference_path.get()}"); return
        self.save_settings()
        python = NUNO_TOUKA_DIR / ".venv" / "Scripts" / "python.exe"
        if not python.is_file(): python = Path(sys.executable)
        script = NUNO_TOUKA_DIR / "touka_batch.py"
        preset = OBJECT_PRESET_LABELS.get(self.object_preset.get(), "generic")
        surface_preset = TRANSPARENT_TARGET_PRESET_LABELS.get(self.surface_preset.get(), "auto")
        cpu_cores = self.cpu_cores.get().strip()
        command = [str(python), str(script), "--mode", self.mode.get(), "--profile", self.profile.get(), "--object-preset", preset, "--surface-preset", surface_preset, "--preview-start-seconds", str(preview_start), "--preview-seconds", str(preview_seconds), "--input", str(source), "--output", str(target)]
        if self.roi.get().strip(): command.extend(["--roi", self.roi.get().strip()])
        if self.reference_path.get().strip(): command.extend(["--reference-dir", self.reference_path.get().strip()])
        if self.surface_reference_path.get().strip(): command.extend(["--surface-reference-dir", self.surface_reference_path.get().strip()])
        if self.denoise_references.get(): command.append("--denoise-reference")
        def worker():
            try:
                self.process = subprocess.Popen(command, cwd=str(NUNO_TOUKA_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
                self.logbox.log(ProcessCpuLimiter.apply(self.process.pid, cpu_cores))
                for line in self.process.stdout or []: self.logbox.log(line.rstrip())
                code = self.process.wait(); self.logbox.log(f"完了 (code={code})")
                if code == 0:
                    history_dir = self.evaluation_path.get().strip() or str(Path(self.output_path.get()) / "evaluation_history")
                    evaluator = ToukaEvaluator(); record = evaluator.evaluate(str(source), str(target), self.profile.get(), self.object_preset.get())
                    history = evaluator.write_history(history_dir, record)
                    self.logbox.log(f"評価履歴を保存しました: {history}")
            except Exception as exc: self.logbox.log(f"エラー: {exc}")
        _safe_thread(self.logbox, worker)

    def stop(self):
        if self.process and self.process.poll() is None: self.process.terminate(); self.logbox.log("停止要求を送信しました")
