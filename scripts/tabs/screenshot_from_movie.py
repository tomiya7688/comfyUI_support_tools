import json
import os
import random
import subprocess
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tkinter import ttk

from comfyui_support_tools.shared.contracts.frame_filter import (
    FrameFilterAction,
    FrameFilterOptions,
    FrameFilterPreset,
)
from comfyui_support_tools.shared.frame_filter_application import filter_existing_frame_folder

from ..backend.process_cpu_limiter import ProcessCpuLimiter
from ..context import USER_PATHS, _safe_thread
from ..widgets.labeled_path_row import LabeledPathRow
from ..widgets.log_box import LogBox
from ..widgets.preset_store import PresetStore


class ScreenshotFromMovieTab(ttk.Frame):
    DEFAULT_INPUT_DIR = USER_PATHS["screenshot_input_dir"]
    DEFAULT_OUTPUT_DIR = USER_PATHS["screenshot_output_dir"]
    VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v")

    def __init__(self, master):
        super().__init__(master, padding=10)
        self.input_dir = tk.StringVar(value=self.DEFAULT_INPUT_DIR)
        self.output_dir = tk.StringVar(value=self.DEFAULT_OUTPUT_DIR)
        self.existing_frames_dir = tk.StringVar(value="")
        self.frames = tk.StringVar(value="100")
        self.image_format = tk.StringVar(value="jpg")
        self.max_workers = tk.StringVar(value=str(max(1, (os.cpu_count() or 4) // 2)))
        self.cpu_cores = tk.StringVar(value=str(max(1, (os.cpu_count() or 4) // 2)))
        self.low_priority = tk.BooleanVar(value=True)
        self.filter_enabled = tk.BooleanVar(value=False)
        self.filter_preset = tk.StringVar(value=FrameFilterPreset.CONSERVATIVE.value)
        self.filter_action = tk.StringVar(value=FrameFilterAction.REVIEW_QUEUE.value)
        self.title_credits_policy = tk.StringVar(value="keep")
        self.filter_preview_only = tk.BooleanVar(value=True)
        self.custom_extreme_ratio = tk.StringVar(value="0.995")
        self.custom_candidate = tk.StringVar(value="0.86")
        self.custom_title = tk.StringVar(value="0.90")
        self.custom_protect = tk.StringVar(value="0.08")
        self.filter_rules = {
            key: tk.BooleanVar(value=True)
            for key in (
                "black",
                "white",
                "transition",
                "text_only",
                "title_credits",
                "low_detail",
                "blur",
                "neighbors",
            )
        }
        self.preset_store = PresetStore("screenshot_from_movie")
        self.preset_name = tk.StringVar()
        LabeledPathRow(self, "INPUT_DIR", self.input_dir, mode="dir").pack(fill="x", pady=4)
        LabeledPathRow(self, "OUTPUT_DIR", self.output_dir, mode="dir").pack(fill="x", pady=4)
        existing_frames_row = ttk.Frame(self)
        existing_frames_row.pack(fill="x", pady=4)
        ttk.Label(existing_frames_row, text="既存フレームフォルダー").pack(side="left")
        ttk.Entry(existing_frames_row, textvariable=self.existing_frames_dir).pack(
            side="left", fill="x", expand=True, padx=6
        )
        row = ttk.Frame(self)
        row.pack(fill="x", pady=4)
        for label, var in [
            ("FRAMES_PER_VIDEO", self.frames),
            ("IMAGE_FORMAT", self.image_format),
            ("MAX_WORKERS", self.max_workers),
        ]:
            ttk.Label(row, text=label).pack(side="left")
            ttk.Entry(row, textvariable=var, width=8).pack(side="left", padx=(4, 12))
        row2 = ttk.Frame(self)
        row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="使用CPU論理数").pack(side="left")
        ttk.Entry(row2, textvariable=self.cpu_cores, width=8).pack(side="left", padx=(4, 12))
        ttk.Label(row2, text="空欄なら制限なし").pack(side="left")
        ttk.Checkbutton(self, text="ffmpeg低優先度", variable=self.low_priority).pack(anchor="w")
        filter_row = ttk.Frame(self)
        filter_row.pack(fill="x", pady=4)
        ttk.Checkbutton(
            filter_row,
            text="低情報フレームを解析（既定OFF・原本保持）",
            variable=self.filter_enabled,
        ).pack(side="left")
        ttk.Label(filter_row, text="preset").pack(side="left", padx=(12, 4))
        ttk.Combobox(
            filter_row,
            textvariable=self.filter_preset,
            width=14,
            state="readonly",
            values=tuple(item.value for item in FrameFilterPreset),
        ).pack(side="left")
        ttk.Label(filter_row, text="action").pack(side="left", padx=(12, 4))
        ttk.Combobox(
            filter_row,
            textvariable=self.filter_action,
            width=18,
            state="readonly",
            values=tuple(item.value for item in FrameFilterAction),
        ).pack(side="left")
        ttk.Label(filter_row, text="title/credits").pack(side="left", padx=(12, 4))
        ttk.Combobox(
            filter_row,
            textvariable=self.title_credits_policy,
            width=10,
            state="readonly",
            values=("keep", "drop", "separate"),
        ).pack(side="left")
        ttk.Checkbutton(filter_row, text="preview only", variable=self.filter_preview_only).pack(
            side="left", padx=(12, 4)
        )
        rule_row = ttk.Frame(self)
        rule_row.pack(fill="x", pady=2)
        rule_labels = {
            "black": "black",
            "white": "white",
            "transition": "fade/transition",
            "text_only": "text only (OCR evidence)",
            "title_credits": "title/credits",
            "low_detail": "low detail",
            "blur": "blur outlier",
            "neighbors": "neighbor compare",
        }
        for key, label in rule_labels.items():
            ttk.Checkbutton(rule_row, text=label, variable=self.filter_rules[key]).pack(
                side="left", padx=2
            )
        threshold_row = ttk.Frame(self)
        threshold_row.pack(fill="x", pady=2)
        for label, variable in (
            ("custom extreme ratio", self.custom_extreme_ratio),
            ("candidate", self.custom_candidate),
            ("title", self.custom_title),
            ("structure protect", self.custom_protect),
        ):
            ttk.Label(threshold_row, text=label).pack(side="left", padx=(4, 2))
            ttk.Entry(threshold_row, textvariable=variable, width=6).pack(side="left", padx=(0, 6))
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="Start", command=lambda: _safe_thread(self.logbox, self.run)).pack(
            side="left"
        )
        ttk.Button(
            buttons,
            text="Filter existing frames",
            command=lambda: _safe_thread(self.logbox, self.filter_existing_frames),
        ).pack(side="left", padx=4)
        ttk.Label(buttons, text="preset").pack(side="left", padx=(16, 4))
        self.preset_combo = ttk.Combobox(buttons, textvariable=self.preset_name, width=18)
        self.preset_combo.pack(side="left")
        ttk.Button(buttons, text="保存", command=self.save_preset).pack(side="left", padx=4)
        ttk.Button(buttons, text="読込", command=self.load_preset).pack(side="left", padx=4)
        self.logbox = LogBox(self)
        self.logbox.pack(fill="both", expand=True)
        self._refresh_preset_choices()

    def _refresh_preset_choices(self):
        self.preset_combo.configure(values=self.preset_store.names())

    def save_preset(self):
        try:
            values = {
                "input_dir": self.input_dir.get(),
                "output_dir": self.output_dir.get(),
                "existing_frames_dir": self.existing_frames_dir.get(),
                "frames": self.frames.get(),
                "image_format": self.image_format.get(),
                "max_workers": self.max_workers.get(),
                "cpu_cores": self.cpu_cores.get(),
                "low_priority": self.low_priority.get(),
                "filter_enabled": self.filter_enabled.get(),
                "filter_preset": self.filter_preset.get(),
                "filter_action": self.filter_action.get(),
                "title_credits_policy": self.title_credits_policy.get(),
                "filter_preview_only": self.filter_preview_only.get(),
                "filter_rules": {key: value.get() for key, value in self.filter_rules.items()},
                "custom_extreme_ratio": self.custom_extreme_ratio.get(),
                "custom_candidate": self.custom_candidate.get(),
                "custom_title": self.custom_title.get(),
                "custom_protect": self.custom_protect.get(),
            }
            path = self.preset_store.save(self.preset_name.get(), values)
            self.preset_name.set(path.stem)
            self._refresh_preset_choices()
            self.logbox.log(f"プリセットを保存しました: {path}")
        except Exception as error:
            self.logbox.log(f"プリセット保存エラー: {error}")

    def load_preset(self):
        try:
            values = self.preset_store.load(self.preset_name.get())
            self.input_dir.set(values.get("input_dir", self.input_dir.get()))
            self.output_dir.set(values.get("output_dir", self.output_dir.get()))
            self.existing_frames_dir.set(
                values.get("existing_frames_dir", self.existing_frames_dir.get())
            )
            self.frames.set(str(values.get("frames", self.frames.get())))
            self.image_format.set(values.get("image_format", self.image_format.get()))
            self.max_workers.set(str(values.get("max_workers", self.max_workers.get())))
            self.cpu_cores.set(str(values.get("cpu_cores", self.cpu_cores.get())))
            self.low_priority.set(bool(values.get("low_priority", self.low_priority.get())))
            self.filter_enabled.set(bool(values.get("filter_enabled", False)))
            self.filter_preset.set(
                values.get("filter_preset", FrameFilterPreset.CONSERVATIVE.value)
            )
            self.filter_action.set(
                values.get("filter_action", FrameFilterAction.REVIEW_QUEUE.value)
            )
            self.title_credits_policy.set(values.get("title_credits_policy", "keep"))
            self.filter_preview_only.set(bool(values.get("filter_preview_only", True)))
            saved_rules = values.get("filter_rules", {})
            for key, value in self.filter_rules.items():
                value.set(bool(saved_rules.get(key, True)))
            self.custom_extreme_ratio.set(values.get("custom_extreme_ratio", "0.995"))
            self.custom_candidate.set(values.get("custom_candidate", "0.86"))
            self.custom_title.set(values.get("custom_title", "0.90"))
            self.custom_protect.set(values.get("custom_protect", "0.08"))
            self.logbox.log("プリセットを読み込みました")
        except Exception as error:
            self.logbox.log(f"プリセット読込エラー: {error}")

    def _duration(self, path):
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=True,
        )
        return float(json.loads(p.stdout)["format"]["duration"])

    def _low_kwargs(self):
        if not self.low_priority.get():
            return {}
        if os.name == "nt":
            return {"creationflags": 0x00000040}
        return {"preexec_fn": lambda: os.nice(19)}

    def _extract(self, video, ts, out, cpu_cores):
        os.makedirs(os.path.dirname(out), exist_ok=True)
        cmd = ["ffmpeg", "-y", "-ss", f"{ts:.6f}", "-i", video, "-frames:v", "1", "-q:v", "2", out]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **self._low_kwargs()
        )
        ProcessCpuLimiter.apply(proc.pid, cpu_cores)
        return_code = proc.wait()
        if return_code != 0:
            raise RuntimeError(f"FFmpeg frame extraction failed at {ts:.3f}s (exit {return_code})")

    # {
    #   責務: [_filter_options: UI選択を共通FrameFilterOptionsへ解決する]
    #   処理: [1: preset/action/policyをenumへ変換する 2: individual rule togglesを反映する]
    #   引数: []
    #   戻り値: [enabled FrameFilterOptions]
    # }
    def _filter_options(self):
        return FrameFilterOptions(
            enabled=True,
            preset=FrameFilterPreset(self.filter_preset.get()),
            action=FrameFilterAction(self.filter_action.get()),
            title_credits_policy=self.title_credits_policy.get(),
            detect_black=self.filter_rules["black"].get(),
            detect_white=self.filter_rules["white"].get(),
            detect_transition=self.filter_rules["transition"].get(),
            detect_text_only=self.filter_rules["text_only"].get(),
            detect_title_credits=self.filter_rules["title_credits"].get(),
            detect_low_detail=self.filter_rules["low_detail"].get(),
            detect_blur=self.filter_rules["blur"].get(),
            compare_neighbors=self.filter_rules["neighbors"].get(),
            custom_extreme_ratio_threshold=float(self.custom_extreme_ratio.get()),
            custom_candidate_threshold=float(self.custom_candidate.get()),
            custom_title_threshold=float(self.custom_title.get()),
            custom_information_protection_threshold=float(self.custom_protect.get()),
        )

    # {
    #   責務: [filter_existing_frames: 既存frame folderをpreviewまたは非破壊copy filterする]
    #   処理: [1: input/output pathを解決する 2: shared filter serviceを呼ぶ 3: result summaryをlogへ出す]
    #   引数: []
    #   戻り値: []
    # }
    def filter_existing_frames(self):
        source_value = self.existing_frames_dir.get().strip()
        if not source_value:
            self.logbox.log("既存フレームフォルダーを指定してください")
            return
        source = Path(source_value).expanduser()
        output = Path(self.output_dir.get().strip()).expanduser() / "filtered_frames"
        try:
            report = filter_existing_frame_folder(
                source,
                output,
                self._filter_options(),
                dry_run=self.filter_preview_only.get(),
            )
            self.logbox.log(
                f"existing frame filter{' preview' if self.filter_preview_only.get() else ''}: "
                f"keep={report.kept_count}, drop={report.dropped_count}, "
                f"review={report.review_count}, error={report.error_count}; output={output}"
            )
            if not self.filter_preview_only.get():
                self.logbox.log(f"manifest: {output / 'frame_filter_manifest.json'}")
        except Exception as error:
            self.logbox.log(f"既存frame filterエラー: {error}")

    def run(self):
        inp = self.input_dir.get().strip()
        outroot = self.output_dir.get().strip()
        frames = int(self.frames.get())
        fmt = self.image_format.get().strip().lower()
        workers = max(1, int(self.max_workers.get()))
        cpu_cores = self.cpu_cores.get().strip()
        try:
            cpu_count = ProcessCpuLimiter.core_count(cpu_cores)
        except ValueError:
            self.logbox.log(f"使用CPU論理数には数値を指定してください: {cpu_cores}")
            return
        if fmt == "jpeg":
            fmt = "jpg"
        if fmt not in ("jpg", "png"):
            self.logbox.log("IMAGE_FORMAT は jpg/png/jpeg")
            return
        if not os.path.isdir(inp):
            self.logbox.log(f"入力フォルダがありません: {inp}")
            return
        self.logbox.log(
            "CPU制限: なし" if cpu_count is None else f"CPU制限: 論理CPU 0-{cpu_count - 1}"
        )
        os.makedirs(outroot, exist_ok=True)
        videos = [f for f in os.listdir(inp) if f.lower().endswith(self.VIDEO_EXTS)]
        self.logbox.log(f"動画数: {len(videos)}")
        for f in videos:
            try:
                video = os.path.join(inp, f)
                dur = self._duration(video)
                name = Path(video).stem[:180]
                outdir = os.path.join(outroot, name)
                os.makedirs(outdir, exist_ok=True)
                times = sorted(
                    random.sample([random.uniform(0, dur) for _ in range(frames * 2)], frames)
                )
                self.logbox.log(f"Processing: {video}")
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futs = [
                        ex.submit(
                            self._extract,
                            video,
                            ts,
                            os.path.join(outdir, f"frame_{i:03d}.{fmt}"),
                            cpu_cores,
                        )
                        for i, ts in enumerate(times)
                    ]
                    for fu in as_completed(futs):
                        fu.result()
                if self.filter_enabled.get():
                    filter_options = self._filter_options()
                    filtered_dir = Path(outdir).with_name(f"{Path(outdir).name}_filtered")
                    report = filter_existing_frame_folder(
                        Path(outdir),
                        filtered_dir,
                        filter_options,
                        dry_run=self.filter_preview_only.get(),
                    )
                    self.logbox.log(
                        f"filter{' preview' if self.filter_preview_only.get() else ''}: "
                        f"keep={report.kept_count}, drop={report.dropped_count}, "
                        f"review={report.review_count}, error={report.error_count}; "
                        f"原本={outdir}; 出力={filtered_dir}"
                    )
                self.logbox.log(f"完了: {f}")
            except Exception as e:
                self.logbox.log(f"❌ {f}: {e}")
        self.logbox.log("全処理完了")
