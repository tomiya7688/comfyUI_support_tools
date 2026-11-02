"""Tk review window for task-aware LoRA dataset curation."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from comfyui_support_tools.applications.lora_dataset_curator import DatasetCuratorApplication
from comfyui_support_tools.shared.contracts.dataset_curator import (
    CaptionPolicy,
    CropPolicy,
    CuratorConfig,
    CuratorTask,
    DatasetAnalysis,
    OutlierClass,
    SampleAction,
    SampleOverride,
)


# {
# 責務: [DatasetCuratorWindow: provide visual review/edit/export controls]
# フィールド: [application, analysis, overrides, worker result queue]
# 処理: [let users choose task and trainer, review coverage/splits, override Auto choices, and export a trainer folder]
# }
class DatasetCuratorWindow(tk.Tk):
    # {
    # 責務: [__init__: build the dataset curation review interface]
    # 処理: [create inputs, review table, caption ownership controls and asynchronous action polling]
    # 引数: [self: window instance, application: injectable Application boundary]
    # 戻り値: [None: window initialized]
    # }
    def __init__(self, application: DatasetCuratorApplication | None = None) -> None:
        super().__init__()
        self.title("LoRA Dataset Curator / Caption Planner")
        self.geometry("1100x720")
        self.application = application or DatasetCuratorApplication()
        self.analysis: DatasetAnalysis | None = None
        self.overrides: dict[str, SampleOverride] = {}
        self.results: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.root_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.task_var = tk.StringVar(value=CuratorTask.CHARACTER.value)
        self.caption_policy_var = tk.StringVar(value=CaptionPolicy.HYBRID.value)
        self.crop_policy_var = tk.StringVar(value=CropPolicy.PRESERVE.value)
        self.validation_ratio_var = tk.StringVar(value="0.2")
        self.seed_var = tk.StringVar(value="1729")
        self.fixed_clothing_var = tk.BooleanVar(value=False)
        self.trainer_var = tk.StringVar(value="sd-scripts")
        self.status_var = tk.StringVar(value="データセットを選び、Analyzeを押してください。")
        self.concept_var = tk.StringVar()
        self.variable_var = tk.StringVar()
        self.weight_var = tk.StringVar()
        self.split_var = tk.StringVar(value="Auto")
        self.outlier_var = tk.StringVar(value="Auto")
        self._build_widgets()
        self.after(150, self._poll_results)

    # {
    # 責務: [_build_widgets: assemble dataset paths, task controls and sample review table]
    # 処理: [create path pickers, task/trainer selectors, override editors, and coverage/results panels]
    # 引数: [self: current window]
    # 戻り値: [None: widgets packed]
    # }
    def _build_widgets(self) -> None:
        paths = ttk.Frame(self, padding=8)
        self._build_path_controls(paths)
        paths.pack(fill="x")
        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True, padx=8)
        self._build_review_table(body)
        self._build_override_editor(body)
        footer = ttk.Frame(self, padding=8)
        footer.pack(fill="x")
        self.export_button = ttk.Button(
            footer, text="Export dataset", command=self._export, state="disabled"
        )
        self.export_button.pack(side="right")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left", fill="x", expand=True)

    # {
    # 責務: [_build_path_controls: create source/target and task configuration inputs]
    # 処理: [build path pickers, task/trainer selectors, caption/crop policies, split seed and character clothing option]
    # 引数: [self: window, parent: path control frame]
    # 戻り値: [None: path controls are populated]
    # }
    def _build_path_controls(self, paths: ttk.Frame) -> None:
        ttk.Label(paths, text="Dataset").grid(row=0, column=0, sticky="w")
        ttk.Entry(paths, textvariable=self.root_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(paths, text="Browse…", command=self._choose_root).grid(row=0, column=2)
        ttk.Label(paths, text="Export to").grid(row=1, column=0, sticky="w")
        ttk.Entry(paths, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(paths, text="Browse…", command=self._choose_output).grid(row=1, column=2)
        ttk.Label(paths, text="Task").grid(row=2, column=0, sticky="w")
        ttk.Combobox(
            paths,
            textvariable=self.task_var,
            values=[item.value for item in CuratorTask],
            state="readonly",
            width=18,
        ).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Label(paths, text="Trainer").grid(row=2, column=1, sticky="e", padx=(0, 180))
        ttk.Combobox(
            paths,
            textvariable=self.trainer_var,
            values=("sd-scripts", "simpletuner", "ai-toolkit"),
            state="readonly",
            width=18,
        ).grid(row=2, column=1, sticky="e", padx=6)
        self.analyze_button = ttk.Button(paths, text="Analyze / Re-analyze", command=self._analyze)
        self.analyze_button.grid(row=2, column=2, sticky="ew", pady=4)
        ttk.Label(paths, text="Caption").grid(row=3, column=0, sticky="w")
        ttk.Combobox(
            paths,
            textvariable=self.caption_policy_var,
            values=[item.value for item in CaptionPolicy],
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Label(paths, text="Crop").grid(row=3, column=1, sticky="e", padx=(0, 290))
        ttk.Combobox(
            paths,
            textvariable=self.crop_policy_var,
            values=[item.value for item in CropPolicy],
            state="readonly",
            width=18,
        ).grid(row=3, column=1, sticky="e", padx=180)
        ttk.Label(paths, text="Validation ratio").grid(row=4, column=0, sticky="w")
        ttk.Entry(paths, textvariable=self.validation_ratio_var, width=8).grid(
            row=4, column=1, sticky="w", padx=6
        )
        ttk.Label(paths, text="Seed").grid(row=4, column=1, sticky="e", padx=(0, 290))
        ttk.Entry(paths, textvariable=self.seed_var, width=10).grid(
            row=4, column=1, sticky="e", padx=180
        )
        ttk.Checkbutton(
            paths,
            text="Character identity keeps clothing fixed",
            variable=self.fixed_clothing_var,
        ).grid(row=5, column=1, sticky="w", padx=6)
        paths.columnconfigure(1, weight=1)

    # {
    # 責務: [_build_review_table: create per-image review grid]
    # 処理: [display action, group split, weight, outlier and selected caption with selection/double-click handlers]
    # 引数: [self: window, body: vertical content pane]
    # 戻り値: [None: review grid added]
    # }
    def _build_review_table(self, body: ttk.Panedwindow) -> None:
        table_frame = ttk.Frame(body)
        columns = ("action", "split", "weight", "outlier", "caption")
        self.samples = ttk.Treeview(
            table_frame, columns=columns, show="tree headings", selectmode="browse"
        )
        self.samples.heading("#0", text="Image")
        self.samples.column("#0", width=190)
        for key, title, width in (
            ("action", "Action", 90),
            ("split", "Split", 90),
            ("weight", "Weight", 70),
            ("outlier", "Review", 145),
            ("caption", "Selected caption", 520),
        ):
            self.samples.heading(key, text=title)
            self.samples.column(key, width=width, stretch=key == "caption")
        self.samples.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.samples.yview)
        scrollbar.pack(side="right", fill="y")
        self.samples.configure(yscrollcommand=scrollbar.set)
        self.samples.bind("<<TreeviewSelect>>", self._select_sample)
        self.samples.bind("<Double-1>", self._cycle_action)
        body.add(table_frame, weight=4)

    # {
    # 責務: [_build_override_editor: create per-image manual controls and coverage report]
    # 処理: [provide caption ownership, weight, split and review coverage controls]
    # 引数: [self: window, body: vertical content pane]
    # 戻り値: [None: override editor added]
    # }
    def _build_override_editor(self, body: ttk.Panedwindow) -> None:
        controls = ttk.Frame(body, padding=8)
        ttk.Label(controls, text="Concept-owned tags (comma separated)").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(controls, textvariable=self.concept_var).grid(
            row=0, column=1, sticky="ew", padx=6
        )
        ttk.Label(controls, text="Variable tags").grid(row=1, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.variable_var).grid(
            row=1, column=1, sticky="ew", padx=6
        )
        ttk.Label(controls, text="Manual sample weight (blank = Auto)").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Entry(controls, textvariable=self.weight_var, width=10).grid(
            row=2, column=1, sticky="w", padx=6
        )
        ttk.Label(controls, text="Split override").grid(row=2, column=1, sticky="e", padx=(0, 180))
        ttk.Combobox(
            controls,
            textvariable=self.split_var,
            values=("Auto", "train", "validation"),
            state="readonly",
            width=14,
        ).grid(row=2, column=1, sticky="e", padx=6)
        ttk.Label(controls, text="Outlier review").grid(row=3, column=0, sticky="w")
        ttk.Combobox(
            controls,
            textvariable=self.outlier_var,
            values=("Auto", *(item.value for item in OutlierClass)),
            state="readonly",
            width=24,
        ).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Button(
            controls, text="Apply caption override", command=self._apply_caption_override
        ).grid(row=0, column=2, rowspan=3, padx=6)
        self.coverage = tk.Text(controls, height=5, state="disabled", wrap="word")
        self.coverage.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=6)
        controls.columnconfigure(1, weight=1)
        controls.rowconfigure(4, weight=1)
        body.add(controls, weight=1)

    # {
    # 責務: [_choose_root: ask for the source dataset directory]
    # 処理: [open a directory picker and suggest an export sibling]
    # 引数: [self: current window]
    # 戻り値: [None: selected paths displayed]
    # }
    def _choose_root(self) -> None:
        chosen = filedialog.askdirectory(title="LoRA dataset directory")
        if chosen:
            self.root_var.set(chosen)
            self.output_var.set(str(Path(chosen).with_name(f"{Path(chosen).name}-curated")))

    # {
    # 責務: [_choose_output: ask for the new export directory]
    # 処理: [open a directory picker for an existing parent directory]
    # 引数: [self: current window]
    # 戻り値: [None: destination parent selected]
    # }
    def _choose_output(self) -> None:
        chosen = filedialog.askdirectory(title="Export parent directory")
        if chosen:
            self.output_var.set(str(Path(chosen) / "curated-lora-dataset"))

    # {
    # 責務: [_analyze: launch dataset inspection with current manual overrides]
    # 処理: [validate required paths, run image analysis off the UI thread, and disable overlapping actions]
    # 引数: [self: current window]
    # 戻り値: [None: analysis scheduled]
    # }
    def _analyze(self) -> None:
        root = self.root_var.get().strip()
        if not root:
            self.status_var.set("Dataset directory is required.")
            return
        try:
            config = CuratorConfig(
                CuratorTask(self.task_var.get()),
                caption_policy=CaptionPolicy(self.caption_policy_var.get()),
                crop_policy=CropPolicy(self.crop_policy_var.get()),
                validation_ratio=float(self.validation_ratio_var.get()),
                seed=int(self.seed_var.get()),
                fixed_clothing=self.fixed_clothing_var.get(),
            )
        except (ValueError, TypeError) as error:
            self.status_var.set(f"Invalid curation options: {error}")
            return
        overrides = tuple(self.overrides.values())

        # {
        # 責務: [run: execute curation away from Tk's event thread]
        # 処理: [return either analysis or a bounded error message through the result queue]
        # 引数: [self: current window, root: source directory, config: selected task, overrides: current edits]
        # 戻り値: [None: result queued]
        # }
        def run() -> None:
            try:
                self.results.put(
                    ("analysis", self.application.curate(root, config, overrides=overrides))
                )
            except Exception as error:  # noqa: BLE001 - UI reports the user's operation error
                self.results.put(("error", str(error)))

        self.analyze_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.status_var.set("Inspecting images and planning splits…")
        threading.Thread(target=run, daemon=True, name="lora-dataset-analysis").start()

    # {
    # 責務: [_export: export the reviewed analysis to the selected trainer]
    # 処理: [run atomic Data layer export on a worker thread]
    # 引数: [self: current window]
    # 戻り値: [None: export scheduled]
    # }
    def _export(self) -> None:
        if self.analysis is None:
            return
        destination = self.output_var.get().strip()
        if not destination:
            self.status_var.set("Export destination is required.")
            return
        analysis = self.analysis
        trainer = self.trainer_var.get()

        # {
        # 責務: [run: export without blocking Tk's event loop]
        # 処理: [queue completed export path or failure text]
        # 引数: [self: current window, analysis: reviewed plan, destination: new path, trainer: selected format]
        # 戻り値: [None: result queued]
        # }
        def run() -> None:
            try:
                self.results.put(
                    ("export", self.application.export(analysis, destination, trainer))
                )
            except Exception as error:  # noqa: BLE001 - UI reports the user's operation error
                self.results.put(("error", str(error)))

        self.export_button.configure(state="disabled")
        self.status_var.set("Copying and verifying selected files…")
        threading.Thread(target=run, daemon=True, name="lora-dataset-export").start()

    # {
    # 責務: [_poll_results: apply worker results on Tk's event thread]
    # 処理: [update sample table, coverage panel, status, and button states]
    # 引数: [self: current window]
    # 戻り値: [None: UI reflects most recent operation]
    # }
    def _poll_results(self) -> None:
        try:
            kind, value = self.results.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_results)
            return
        if kind == "analysis":
            self.analysis = value
            self._render_analysis(value)
            self.status_var.set(
                f"Analyzed {len(value.samples)} images; fingerprint {value.fingerprint[:16]}"
            )
            self.export_button.configure(state="normal")
            self.analyze_button.configure(state="normal")
        elif kind == "export":
            self.status_var.set(f"Export complete: {value}")
            self.export_button.configure(state="normal" if self.analysis else "disabled")
        else:
            self.status_var.set(f"Operation failed: {value}")
            self.analyze_button.configure(state="normal")
            self.export_button.configure(state="normal" if self.analysis else "disabled")
        self.after(150, self._poll_results)

    # {
    # 責務: [_render_analysis: display per-image decisions and coverage gaps]
    # 処理: [replace rows and show required attribute counts plus warnings]
    # 引数: [self: current window, analysis: curation result]
    # 戻り値: [None: review panels updated]
    # }
    def _render_analysis(self, analysis: DatasetAnalysis) -> None:
        for child in self.samples.get_children():
            self.samples.delete(child)
        for sample in analysis.samples:
            self.samples.insert(
                "",
                "end",
                iid=str(sample.image_path),
                text=sample.image_path.name,
                values=(
                    sample.action.value,
                    sample.split,
                    f"{sample.sample_weight:.2f}",
                    sample.outlier_class.value,
                    sample.captions.trainer_caption,
                ),
            )
        lines = [
            f"{cell.axis}/{cell.label}: {cell.count}{' — MISSING' if cell.missing else ''}"
            for cell in analysis.coverage
        ]
        lines.extend(f"Warning: {warning}" for warning in analysis.warnings)
        self.coverage.configure(state="normal")
        self.coverage.delete("1.0", "end")
        self.coverage.insert("1.0", "\n".join(lines))
        self.coverage.configure(state="disabled")

    # {
    # 責務: [_selected_sample: resolve the selected source image path]
    # 処理: [read the single Treeview selection]
    # 引数: [self: current window]
    # 戻り値: [Path | None: selected source path]
    # }
    def _selected_sample(self) -> Path | None:
        selected = self.samples.selection()
        return Path(selected[0]) if selected else None

    # {
    # 責務: [_select_sample: load editable caption ownership for the selected image]
    # 処理: [show concept-owned and variable tags from the latest analysis]
    # 引数: [self: current window, event: Tk selection event]
    # 戻り値: [None: tag fields updated]
    # }
    def _select_sample(self, event: tk.Event[Any] | None = None) -> None:
        del event
        path = self._selected_sample()
        if path is None or self.analysis is None:
            return
        sample = next((item for item in self.analysis.samples if item.image_path == path), None)
        if sample is None:
            return
        override = self.overrides.get(str(path))
        concept = (
            override.absorb_tags
            if override and override.absorb_tags
            else sample.captions.absorb_tags
        )
        variable = (
            override.variable_tags
            if override and override.variable_tags
            else sample.captions.variable_tags
        )
        self.concept_var.set(", ".join(concept))
        self.variable_var.set(", ".join(variable))
        self.weight_var.set(
            f"{override.weight:g}" if override and override.weight is not None else ""
        )
        self.split_var.set(override.split if override and override.split else "Auto")
        self.outlier_var.set(
            override.outlier_class.value
            if override and override.outlier_class
            else sample.outlier_class.value
        )

    # {
    # 責務: [_cycle_action: cycle the selected image's keep/low-weight/exclude decision]
    # 処理: [store a reversible manual override and re-run analysis]
    # 引数: [self: current window, event: Treeview double-click event]
    # 戻り値: [None: revised analysis scheduled]
    # }
    def _cycle_action(self, event: tk.Event[Any] | None = None) -> None:
        del event
        path = self._selected_sample()
        if path is None or self.analysis is None:
            return
        current = next(
            (item.action for item in self.analysis.samples if item.image_path == path),
            SampleAction.KEEP,
        )
        actions = tuple(SampleAction)
        next_action = actions[(actions.index(current) + 1) % len(actions)]
        prior = self.overrides.get(str(path), SampleOverride(path))
        self.overrides[str(path)] = SampleOverride(
            image_path=path,
            action=next_action,
            weight=prior.weight,
            split=prior.split,
            absorb_tags=prior.absorb_tags,
            variable_tags=prior.variable_tags,
            outlier_class=prior.outlier_class,
        )
        self._analyze()

    # {
    # 責務: [_apply_caption_override: persist manual caption ownership edits]
    # 処理: [parse comma-separated concept/variable labels and recalculate the dataset]
    # 引数: [self: current window]
    # 戻り値: [None: revised analysis scheduled]
    # }
    def _apply_caption_override(self) -> None:
        path = self._selected_sample()
        if path is None:
            self.status_var.set("Select an image before editing caption tags.")
            return
        prior = self.overrides.get(str(path), SampleOverride(path))
        concept = tuple(tag.strip() for tag in self.concept_var.get().split(",") if tag.strip())
        variable = tuple(tag.strip() for tag in self.variable_var.get().split(",") if tag.strip())
        try:
            weight = float(self.weight_var.get()) if self.weight_var.get().strip() else None
        except ValueError:
            self.status_var.set("Manual sample weight must be numeric or blank for Auto.")
            return
        split = self.split_var.get() if self.split_var.get() in {"train", "validation"} else None
        outlier_value = self.outlier_var.get()
        outlier = (
            OutlierClass(outlier_value)
            if outlier_value in {item.value for item in OutlierClass}
            else None
        )
        self.overrides[str(path)] = SampleOverride(
            image_path=path,
            action=prior.action,
            weight=weight,
            split=split,
            absorb_tags=concept,
            variable_tags=variable,
            outlier_class=outlier,
        )
        self._analyze()
