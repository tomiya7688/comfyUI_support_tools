from ..context import *
from ..context import _safe_thread
from ..services import LogBox, LabeledPathRow
from ..backend.process_cpu_limiter import ProcessCpuLimiter
from ..backend.touka_dataset_preset_builder import ToukaDatasetPresetBuilder
from ..backend.touka_evaluator import ToukaEvaluator
from ..widgets.preset_store import PresetStore
from ..widgets.responsive_button_row import ResponsiveButtonRow
from ..subapp_runtime import launch_packaged_executable, packaged_executable
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

# {
#   "責務": "Touka image/video enhancement CLIを操作し対象選択、候補評価、結果表示を管理する。",
#   "フィールド": ["process: 外部処理process", "ranking_data: 選択候補metadata", "preset_store/preset_name: preset", "mode/profile/object_preset/surface_preset: 処理対象設定", "input/output/reference/evaluation paths: 入出力設定", "preview/ROI/CPU variables: 動画範囲と資源設定", "ranking/logbox: 結果表示"]
# }
class ToukaEnhancerTab(ttk.Frame):
    # {
    #   "責務": "Touka enhancement画面の状態を初期化し保存設定を復元する。",
    #   "処理": ["preset・mode・対象・path・video/CPU変数を初期化する", "保存設定を読み込み画面を構築する"],
    #   "引数": {"master": "親Tk widget"}, "戻り値": []
    # }
    def __init__(self, master):
        super().__init__(master, padding=10); self.process = None; self.ranking_data = {}
        self.preset_store = PresetStore("touka"); self.preset_name = tk.StringVar()
        self.mode = tk.StringVar(value="image"); self.profile = tk.StringVar(value="balanced"); self.object_preset = tk.StringVar(value="汎用"); self.surface_preset = tk.StringVar(value="自動推定"); self.cpu_cores = tk.StringVar(); self.preview_seconds = tk.StringVar(value="5"); self.preview_start_seconds = tk.StringVar(value="0"); self.roi = tk.StringVar(); self.input_path = tk.StringVar(); self.output_path = tk.StringVar(); self.reference_path = tk.StringVar(); self.surface_reference_path = tk.StringVar(); self.evaluation_path = tk.StringVar(); self.dataset_preset_name = tk.StringVar(); self.denoise_references = tk.BooleanVar(value=False); self._restore_settings(); self._build()

    # {
    #   "責務": "永続化されたTouka UI設定を既知の変数へ復元する。",
    #   "処理": ["JSON objectを読み取る", "既知keyの型を確認して変数へ設定する"],
    #   "引数": [], "戻り値": []
    # }
    def _restore_settings(self):
        try:
            values = json.loads(TOUKA_SETTINGS_FILE.read_text(encoding="utf-8"))
            if not isinstance(values, dict): return
        except (OSError, ValueError):
            return
        for key, variable in (("mode", self.mode), ("profile", self.profile), ("object_preset", self.object_preset), ("surface_preset", self.surface_preset), ("cpu_cores", self.cpu_cores), ("preview_seconds", self.preview_seconds), ("preview_start_seconds", self.preview_start_seconds), ("roi", self.roi), ("input_path", self.input_path), ("output_path", self.output_path), ("reference_path", self.reference_path), ("surface_reference_path", self.surface_reference_path), ("evaluation_path", self.evaluation_path), ("dataset_preset_name", self.dataset_preset_name), ("denoise_references", self.denoise_references)):
            value = values.get(key)
            if isinstance(value, (str, bool)): variable.set(value)

    # {
    #   "責務": "Touka UI設定をuser config JSONへ保存する。",
    #   "処理": ["現在値をdict化する", "親folderを作りJSONを保存し結果をlogする"],
    #   "引数": [], "戻り値": []
    # }
    def save_settings(self):
        values = {"mode": self.mode.get(), "profile": self.profile.get(), "object_preset": self.object_preset.get(), "surface_preset": self.surface_preset.get(), "cpu_cores": self.cpu_cores.get(), "preview_seconds": self.preview_seconds.get(), "preview_start_seconds": self.preview_start_seconds.get(), "roi": self.roi.get(), "input_path": self.input_path.get(), "output_path": self.output_path.get(), "reference_path": self.reference_path.get(), "surface_reference_path": self.surface_reference_path.get(), "evaluation_path": self.evaluation_path.get(), "dataset_preset_name": self.dataset_preset_name.get(), "denoise_references": self.denoise_references.get()}
        try:
            TOUKA_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            TOUKA_SETTINGS_FILE.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.logbox.log(f"設定を保存しました: {TOUKA_SETTINGS_FILE}")
        except OSError as exc:
            self.logbox.log(f"設定保存エラー: {exc}")

    # {
    #   "責務": "現在のTouka処理設定をpreset dictへまとめる。",
    #   "処理": ["mode/profile/対象/path/範囲/CPU/referenceの設定値を読む"],
    #   "引数": [], "戻り値": "preset保存用dict"
    # }
    def _preset_values(self):
        return {"mode": self.mode.get(), "profile": self.profile.get(), "object_preset": self.object_preset.get(), "surface_preset": self.surface_preset.get(), "cpu_cores": self.cpu_cores.get(), "preview_seconds": self.preview_seconds.get(), "preview_start_seconds": self.preview_start_seconds.get(), "roi": self.roi.get(), "input_path": self.input_path.get(), "output_path": self.output_path.get(), "reference_path": self.reference_path.get(), "surface_reference_path": self.surface_reference_path.get(), "evaluation_path": self.evaluation_path.get(), "dataset_preset_name": self.dataset_preset_name.get(), "denoise_references": self.denoise_references.get()}

    # {
    #   "責務": "Touka preset一覧を選択widgetへ反映する。",
    #   "処理": ["PresetStoreのnamesをcombobox候補へ設定する"],
    #   "引数": [], "戻り値": []
    # }
    def _refresh_preset_choices(self): self.preset_combo.configure(values=self.preset_store.names())

    # {
    #   "責務": "現在のTouka処理設定を名前付きpresetとして保存する。",
    #   "処理": ["設定値を保存し選択肢とlogを更新する", "失敗をlogへ出す"],
    #   "引数": [], "戻り値": []
    # }
    def save_preset(self):
        try:
            path = self.preset_store.save(self.preset_name.get(), self._preset_values()); self.preset_name.set(path.stem); self._refresh_preset_choices(); self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error: self.logbox.log(f"プリセット保存エラー: {error}")

    # {
    #   "責務": "選択Touka presetの値を対応する画面変数へ復元する。",
    #   "処理": ["保存済み各keyを現在値へ反映する", "結果をlogへ出す"],
    #   "引数": [], "戻り値": []
    # }
    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            for key, variable in (("mode", self.mode), ("profile", self.profile), ("object_preset", self.object_preset), ("surface_preset", self.surface_preset), ("cpu_cores", self.cpu_cores), ("preview_seconds", self.preview_seconds), ("preview_start_seconds", self.preview_start_seconds), ("roi", self.roi), ("input_path", self.input_path), ("output_path", self.output_path), ("reference_path", self.reference_path), ("surface_reference_path", self.surface_reference_path), ("evaluation_path", self.evaluation_path), ("dataset_preset_name", self.dataset_preset_name), ("denoise_references", self.denoise_references)):
                if key in values: variable.set(values[key])
            self.logbox.log("プリセットを読み込みました")
        except Exception as error: self.logbox.log(f"プリセット読込エラー: {error}")

    # {
    #   "責務": "Toukaのimage/video条件、対象/reference指定、結果操作UIを構築する。",
    #   "処理": ["mode/profile/対象と入出力条件を配置する", "選択・診断・ランキング・実行操作とlogを配置する"],
    #   "引数": [], "戻り値": []
    # }
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

    # {
    #   "責務": "同梱Touka Editorがあれば起動する。",
    #   "処理": ["実行fileの有無を確認し起動または案内をlogへ出す"],
    #   "引数": [], "戻り値": []
    # }
    def open_editor(self):
        executable = packaged_executable("ToukaEditor")
        if not executable.is_file():
            self.logbox.log(f"Touka Editor が未導入です: {executable}")
            return
        try:
            launch_packaged_executable(executable)
            self.logbox.log("画像編集画面を起動しました。Auto objectはその画面上部にあります。")
        except Exception as exc:
            self.logbox.log(f"起動エラー: {exc}")

    # {
    #   "責務": "Touka関連同梱実行fileの導入状況をlogへ表示する。",
    #   "処理": ["各executable pathを検査し存在状態を出力する"],
    #   "引数": [], "戻り値": []
    # }
    def diagnose_environment(self):
        executables = (
            ("Touka", packaged_executable("Touka")),
            ("Touka Editor", packaged_executable("ToukaEditor")),
            ("Touka Fashionpedia Presets", packaged_executable("ToukaFashionpediaPresets")),
        )
        for label, executable in executables:
            if executable.is_file():
                self.logbox.log(f"{label}: OK / {executable}")
            else:
                self.logbox.log(f"{label}: 未導入 / {executable}")

    # {
    #   "責務": "同梱Fashionpedia preset builderを安全threadで起動する。",
    #   "処理": ["executableを検査する", "builder実行をsafe threadへ依頼する"],
    #   "引数": [], "戻り値": []
    # }
    def create_fashionpedia_presets(self):
        executable = packaged_executable("ToukaFashionpediaPresets")
        if not executable.is_file():
            self.logbox.log(f"Touka Fashionpedia Presets が未導入です: {executable}")
            return
        self.logbox.log("FashionpediaからToukaプリセットを作成します")
        _safe_thread(self.logbox, self._run_fashionpedia_preset_builder, executable)

    # {
    #   "責務": "Fashionpedia preset builderを実行し完了結果をGUI threadへ渡す。",
    #   "処理": ["subprocessを起動しstdout/stderrを取得する", "失敗を報告し成功時は完了callbackを予約する"],
    #   "引数": {"executable": "builder executable path"}, "戻り値": []
    # }
    def _run_fashionpedia_preset_builder(self, executable):
        result = subprocess.run([str(executable)], cwd=str(executable.parent), capture_output=True, text=True, encoding="utf-8", errors="replace")
        message = result.stdout.strip() or result.stderr.strip()
        if result.returncode != 0:
            self.after(0, lambda: self.logbox.log(f"Fashionpediaプリセット作成エラー: {message}"))
            return
        self.after(0, lambda: self._finish_fashionpedia_preset_builder(message))

    # {
    #   "責務": "Fashionpedia preset builder成功結果をUIへ通知する。",
    #   "処理": ["preset choicesを更新し完了messageをlogへ出す"],
    #   "引数": {"message": "builder標準出力または完了情報"}, "戻り値": []
    # }
    def _finish_fashionpedia_preset_builder(self, message):
        self._refresh_preset_choices()
        self.logbox.log(f"Fashionpediaプリセットを作成しました\n{message}")

    # {
    #   "責務": "強調対象参考画像群からdataset presetを作成して保存する。",
    #   "処理": ["reference画像と対象presetから値を抽出する", "presetを保存し画像件数とpathをlogする"],
    #   "引数": [], "戻り値": []
    # }
    def create_dataset_preset(self):
        try:
            builder = ToukaDatasetPresetBuilder()
            values = builder.values(self.reference_path.get().strip(), self.object_preset.get())
            path = self.preset_store.save(self.dataset_preset_name.get(), values)
            self.dataset_preset_name.set(path.stem); self._refresh_preset_choices()
            self.logbox.log(f"データセットプリセットを作成しました: {path} / 参考画像 {builder.image_count(self.reference_path.get().strip())} 件")
        except Exception as error:
            self.logbox.log(f"データセットプリセット作成エラー: {error}")

    # {
    #   "責務": "reference画像をToukaで解析し適切な強調対象presetを提案する。",
    #   "処理": ["reference folderとTouka executableを検査する", "解析commandを組みsafe threadへ渡す"],
    #   "引数": [], "戻り値": []
    # }
    def suggest_reference_preset(self):
        reference_dir = Path(self.reference_path.get().strip())
        if not reference_dir.is_dir():
            self.logbox.log(f"強調対象参考画像フォルダが見つかりません: {reference_dir}")
            return
        executable = packaged_executable("Touka")
        if not executable.is_file():
            self.logbox.log(f"Touka が未導入です: {executable}")
            return
        command = [str(executable), "--analyze-reference", "--reference-dir", str(reference_dir)]
        if self.denoise_references.get(): command.append("--denoise-reference")
        _safe_thread(self.logbox, self._read_reference_suggestion, command)

    # {
    #   "責務": "reference解析commandを実行しJSON提案をUIへ反映する。",
    #   "処理": ["subprocess outputを取得する", "return code/JSONを検証して提案callbackを登録する"],
    #   "引数": {"command": "Touka analysis argv"}, "戻り値": []
    # }
    def _read_reference_suggestion(self, command):
        result = subprocess.run(command, cwd=str(Path(command[0]).parent), capture_output=True, text=True, encoding="utf-8", errors="replace")
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

    # {
    #   "責務": "reference解析結果から選択presetと信頼度情報をUIへ適用する。",
    #   "処理": ["提案値を確認して対象選択を更新する", "画像件数、分布、形状一貫性をlogへ示す"],
    #   "引数": {"label": "提案preset", "image_count": "解析画像数", "confidence": "提案信頼度", "distribution": "分類分布", "common_count": "共通検出数", "shape_consistency": "形状一貫性", "outlier_count": "外れ値数"}, "戻り値": []
    # }
    def _apply_reference_suggestion(self, label, image_count, confidence, distribution, common_count=0, shape_consistency=0.0, outlier_count=0):
        self.object_preset.set(label)
        details = ", ".join(f"{key}: {value}" for key, value in distribution.items()) or "有効な形状なし"
        self.logbox.log(f"強調対象参考画像から提案: {label}（解析画像 {image_count} 件、共通候補 {common_count} 件、形状一致 {shape_consistency:.0%}、除外候補 {outlier_count} 件、確信度 {confidence:.0%}、内訳 {details}）")

    # {
    #   "責務": "動画frame上でrectangleを選び対象ROIを正規化座標で保存する。",
    #   "処理": ["動画frameを表示する", "mouse drag rectangleをROIへ変換しUI変数に反映する"],
    #   "引数": [], "戻り値": []
    # }
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
            # {
            #   "責務": "ROI選択canvas上のdrag開始座標を記録する。",
            #   "処理": ["event座標をrectangle状態へ保存する"],
            #   "引数": {"event": "mouse press event"}, "戻り値": []
            # }
            def press(event): state["start"] = (event.x, event.y)
            # {
            #   "責務": "ROI選択中のrectangle previewを更新する。",
            #   "処理": ["既存previewを消しdrag範囲のrectangleを描画する"],
            #   "引数": {"event": "mouse motion event"}, "戻り値": []
            # }
            def drag(event):
                if state["start"]:
                    if state["item"]: canvas.delete(state["item"])
                    state["item"] = canvas.create_rectangle(*state["start"], event.x, event.y, outline="#00ffff", width=2)
            # {
            #   "責務": "mouse release位置から有効ROIを確定する。",
            #   "処理": ["座標をframe boundsにclipする", "正規化ROIを保存しdialogを閉じる"],
            #   "引数": {"event": "mouse release event"}, "戻り値": []
            # }
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

    # {
    #   "責務": "動画先頭frameからAuto objectを抽出しROIと対象presetを設定する。",
    #   "処理": ["frameにGrabCutを適用する", "最大輪郭の形状から対象presetを推定しpreviewを表示する"],
    #   "引数": [], "戻り値": []
    # }
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

    # {
    #   "責務": "動画の候補評価preview範囲をsliderで選択する。",
    #   "処理": ["動画長を取得し範囲選択dialogを開く", "選択区間をUIへ適用する"],
    #   "引数": [], "戻り値": []
    # }
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
            # {
            #   "責務": "slider値をvideo bounds内へ制限してpreview区間を保存する。",
            #   "処理": ["開始・長さをduration内にclipする", "UI値とlogを更新しdialogを閉じる"],
            #   "引数": [], "戻り値": []
            # }
            def apply_range():
                selected_start = min(start.get(), max(0, duration - 0.1)); selected_length = min(length.get(), max(0.1, duration - selected_start))
                self.preview_start_seconds.set(f"{selected_start:.2f}"); self.preview_seconds.set(f"{selected_length:.2f}"); self.logbox.log(f"プレビュー範囲: {selected_start:.2f}秒 から {selected_length:.2f}秒"); dialog.destroy()
            ttk.Button(dialog, text="この範囲を使う", command=apply_range).pack(pady=12)
        except Exception as exc: self.logbox.log(f"プレビュー範囲選択エラー: {exc}")

    # {
    #   "責務": "動画全体からdetailとmotionが高い代表区間を自動選択する。",
    #   "処理": ["各秒のframeを解析しROI内detailとframe差分からscoreを評価する", "最高score周辺をpreview区間に設定する"],
    #   "引数": [], "戻り値": []
    # }
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

    # {
    #   "責務": "現在profileに対応する候補score JSONを既定appで開く。",
    #   "処理": ["output directoryから対象fileを選び存在確認後に開く"],
    #   "引数": [], "戻り値": []
    # }
    def open_scores(self):
        path = Path(self.output_path.get()) / ("candidate_ranking.json" if self.profile.get() == "all" else "candidate_scores.json")
        if not path.is_file(): self.logbox.log(f"ランキングJSONがありません: {path}"); return
        try: os.startfile(str(path))
        except Exception as exc: self.logbox.log(f"ランキング表示エラー: {exc}")

    # {
    #   "責務": "候補比較画像があれば既定image viewerで表示する。",
    #   "処理": ["comparison pathを作り存在確認して開く"],
    #   "引数": [], "戻り値": []
    # }
    def open_comparison(self):
        path = Path(self.output_path.get()) / "candidate_comparison.png"
        if not path.is_file():
            self.logbox.log(f"候補比較画像がありません（候補全生成後に作られます）: {path}"); return
        try: os.startfile(path)
        except Exception as exc: self.logbox.log(f"候補比較画像を開けません: {exc}")

    # {
    #   "責務": "候補ranking JSONを読みTreeviewと選択dataへ反映する。",
    #   "処理": ["rankingを読み行を再構築する", "行IDとitem metadataを対応付ける"],
    #   "引数": [], "戻り値": []
    # }
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

    # {
    #   "責務": "rankingで選択中の生成候補fileを開く。",
    #   "処理": ["行選択とfile存在を検査し既定appで開く"],
    #   "引数": [], "戻り値": []
    # }
    def open_selected_candidate(self):
        selection = self.ranking.selection()
        if not selection: self.logbox.log("ランキングから候補を選択してください"); return
        path = self.ranking.item(selection[0], "values")[5]
        if not Path(path).is_file(): self.logbox.log(f"候補動画が見つかりません: {path}"); return
        try: os.startfile(path)
        except Exception as exc: self.logbox.log(f"候補動画を開けません: {exc}")

    # {
    #   "責務": "rankingで選択中の候補mask previewを開く。",
    #   "処理": ["行選択とmask file存在を検査して既定appで開く"],
    #   "引数": [], "戻り値": []
    # }
    def open_selected_mask(self):
        selection = self.ranking.selection()
        if not selection:
            self.logbox.log("ランキングから候補を選択してください"); return
        path = self.ranking.item(selection[0], "values")[6]
        if not Path(path).is_file():
            self.logbox.log(f"マスクプレビューが見つかりません: {path}"); return
        try: os.startfile(path)
        except Exception as exc: self.logbox.log(f"マスクプレビューを開けません: {exc}")

    # {
    #   "責務": "選択候補のquality・tracking・mask診断値をdialogに表示する。",
    #   "処理": ["ranking itemから診断keyを整形する", "読み取り専用text dialogを表示する"],
    #   "引数": [], "戻り値": []
    # }
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

    # {
    #   "責務": "対応profileの候補をpreviewでなく全尺renderするよう再実行する。",
    #   "処理": ["選択profileを検証する", "開始0秒・長さ0へ設定し処理を始める"],
    #   "引数": [], "戻り値": []
    # }
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

    # {
    #   "責務": "path label、entry、folder/file chooserからなる共通rowを追加する。",
    #   "処理": ["入力変数とdialog種別に接続したwidgetを親へpackする"],
    #   "引数": {"label": "row label", "variable": "path StringVar", "output": "出力選択mode"}, "戻り値": []
    # }
    def _path_row(self, label, variable, output):
        row = ttk.Frame(self); row.pack(fill="x", pady=3); ttk.Label(row, text=label, width=16).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="フォルダ", command=lambda: self._choose_directory(variable, output)).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="ファイル", command=lambda: self._choose_file(variable, output)).pack(side="left", padx=4)

    # {
    #   "責務": "folder chooserからpathを選び指定variableへ設定する。",
    #   "処理": ["入出力に応じたtitleでdirectory dialogを開き選択値を反映する"],
    #   "引数": {"variable": "更新するpath変数", "output": "出力folder選択mode"}, "戻り値": []
    # }
    def _choose_directory(self, variable, output):
        value = filedialog.askdirectory(title="入力フォルダを選択" if not output else "出力フォルダを選択")
        if value: variable.set(value)

    # {
    #   "責務": "modeに応じた画像/動画file chooserを開きpathを設定する。",
    #   "処理": ["入力または出力file dialogを開く", "選択されたfile pathをvariableへ設定する"],
    #   "引数": {"variable": "更新するpath変数", "output": "出力file選択mode"}, "戻り値": []
    # }
    def _choose_file(self, variable, output):
        video_types = [("動画", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("すべて", "*.*")]
        image_types = [("画像", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"), ("すべて", "*.*")]
        if output:
            value = filedialog.asksaveasfilename(title="出力動画ファイルを指定", defaultextension=".mp4", filetypes=video_types)
        else:
            value = filedialog.askopenfilename(title="入力ファイルを選択", filetypes=video_types if self.mode.get() == "video" else image_types)
        if value: variable.set(value)

    # {
    #   "責務": "Touka CLI実行条件を検証しprocess workerを開始する。",
    #   "処理": ["入力・出力・preview・referenceを検証する", "CLI argvを構築しprocess出力と評価履歴を処理するworkerを開始する"],
    #   "引数": [], "戻り値": []
    # }
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
        executable = packaged_executable("Touka")
        if not executable.is_file():
            self.logbox.log(f"Touka が未導入です: {executable}")
            return
        preset = OBJECT_PRESET_LABELS.get(self.object_preset.get(), "generic")
        surface_preset = TRANSPARENT_TARGET_PRESET_LABELS.get(self.surface_preset.get(), "auto")
        cpu_cores = self.cpu_cores.get().strip()
        command = [str(executable), "--mode", self.mode.get(), "--profile", self.profile.get(), "--object-preset", preset, "--surface-preset", surface_preset, "--preview-start-seconds", str(preview_start), "--preview-seconds", str(preview_seconds), "--input", str(source), "--output", str(target)]
        if self.roi.get().strip(): command.extend(["--roi", self.roi.get().strip()])
        if self.reference_path.get().strip(): command.extend(["--reference-dir", self.reference_path.get().strip()])
        if self.surface_reference_path.get().strip(): command.extend(["--surface-reference-dir", self.surface_reference_path.get().strip()])
        if self.denoise_references.get(): command.append("--denoise-reference")
        # {
        #   "責務": "Touka CLIを起動しstdoutをlogして完了後に評価履歴を保存する。",
        #   "処理": ["processを起動しCPU制限を適用する", "出力をlogへ流し正常完了なら評価しhistoryを保存する"],
        #   "引数": [], "戻り値": []
        # }
        def worker():
            try:
                self.process = subprocess.Popen(command, cwd=str(executable.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
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

    # {
    #   "責務": "実行中Touka processへterminate要求を送る。",
    #   "処理": ["processが稼働中なら終了signalを送りlogへ記録する"],
    #   "引数": [], "戻り値": []
    # }
    def stop(self):
        if self.process and self.process.poll() is None: self.process.terminate(); self.logbox.log("停止要求を送信しました")
