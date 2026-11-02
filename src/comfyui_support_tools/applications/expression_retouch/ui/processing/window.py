"""Tk preview, face/region selection, mask refinement, and candidate review."""

from __future__ import annotations

import io
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageOps, ImageTk

from comfyui_support_tools.applications.expression_retouch.ui.commander.application import (
    ExpressionRetouchUiCommander,
)
from comfyui_support_tools.applications.expression_retouch.ui.processing.controls_dialog import (
    ExpressionControlsDialog,
)
from comfyui_support_tools.shared.contracts.expression_retouch import (
    ExpressionEditRequest,
    ExpressionMode,
    ExpressionParameters,
    ExpressionPreset,
    FacePart,
)


# {
#   責務: [ExpressionRetouchWindow: present face-local expression controls and candidate review]
#   フィールド: [selected source/analysis/mask, controls, candidate list, preview and async task state]
#   処理: [load/analyze, preview approximate regions, refine a mask, generate candidates, inspect metadata and differences]
# }
class ExpressionRetouchWindow:
    # {
    #   責務: [__init__: build and initialize the desktop editor]
    #   処理: [1: bind Tk variables, 2: create control and preview panes, 3: load available backend IDs]
    #   引数: [root: Tk root, commander: UI command boundary]
    #   戻り値: []
    # }
    def __init__(self, root: tk.Tk, commander: ExpressionRetouchUiCommander) -> None:
        self.root = root
        self.commander = commander
        self.root.title("Expression Retouch")
        self.root.geometry("1120x780")
        self.source_path: Path | None = None
        self.source_bytes: bytes | None = None
        self.source_image: Image.Image | None = None
        self.analysis = None
        self.manual_mask: Image.Image | None = None
        self.parameters = ExpressionParameters()
        self.mask_edited = False
        self.result = None
        self._preview_image: Image.Image | None = None
        self._preview_photo: ImageTk.PhotoImage | None = None
        self._scale = 1.0
        self._offset = (0, 0)
        self._painting = False
        self._busy = False
        self.input_value = tk.StringVar()
        self.output_value = tk.StringVar()
        self.target_value = tk.StringVar(value=ExpressionPreset.SMILE.value)
        self.mode_value = tk.StringVar(value=ExpressionMode.ANIME.value)
        self.face_value = tk.IntVar(value=0)
        self.intensity_value = tk.DoubleVar(value=0.65)
        self.candidate_count_value = tk.IntVar(value=3)
        self.seed_value = tk.StringVar()
        self.backend_value = tk.StringVar()
        self.status_value = tk.StringVar(
            value="Open an image to detect faces and select edit regions."
        )
        self._build()

    # {
    #   責務: [_build: create the input, editing, and review layout]
    #   処理: [build file controls, face/expression/region controls, preview canvas, candidates and status]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _build(self) -> None:
        outer = ttk.Panedwindow(self.root, orient="horizontal")
        outer.pack(fill="both", expand=True, padx=10, pady=10)
        controls = ttk.Frame(outer, padding=8)
        preview = ttk.Frame(outer, padding=8)
        outer.add(controls, weight=1)
        outer.add(preview, weight=3)
        self._build_controls(controls)
        self.canvas = tk.Canvas(preview, background="#20242a", width=720, height=600)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw_preview())
        self.canvas.bind("<ButtonPress-1>", self._begin_paint)
        self.canvas.bind("<B1-Motion>", lambda event: self._paint(event, 255))
        self.canvas.bind("<ButtonRelease-1>", self._end_paint)
        self.canvas.bind("<ButtonPress-3>", self._begin_paint)
        self.canvas.bind("<B3-Motion>", lambda event: self._paint(event, 0))
        self.canvas.bind("<ButtonRelease-3>", self._end_paint)
        ttk.Label(
            preview,
            text="Left-drag paints the mask; right-drag erases. Outside-mask pixels are restored from source.",
        ).pack(anchor="w")
        self.status = ttk.Label(self.root, textvariable=self.status_value, anchor="w")
        self.status.pack(fill="x", padx=12, pady=(0, 8))

    # {
    #   責務: [_build_controls: create source, expression, mask and candidate controls]
    #   処理: [add browse/analyze actions, target/mode/face controls, region list and generation settings]
    #   引数: [self: window, parent: controls frame]
    #   戻り値: []
    # }
    def _build_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Source image").pack(anchor="w")
        self._path_row(parent, self.input_value, self._choose_source)
        ttk.Label(parent, text="Output workspace").pack(anchor="w", pady=(8, 0))
        self._path_row(parent, self.output_value, self._choose_output)
        ttk.Button(parent, text="Analyze faces", command=self._analyze).pack(fill="x", pady=6)
        ttk.Label(parent, text="Target expression").pack(anchor="w")
        ttk.Combobox(
            parent,
            state="readonly",
            textvariable=self.target_value,
            values=[item.value for item in ExpressionPreset],
        ).pack(fill="x")
        ttk.Label(parent, text="Appearance mode").pack(anchor="w", pady=(8, 0))
        ttk.Combobox(
            parent,
            state="readonly",
            textvariable=self.mode_value,
            values=[item.value for item in ExpressionMode],
        ).pack(fill="x")
        ttk.Label(parent, text="Target face index").pack(anchor="w", pady=(8, 0))
        ttk.Spinbox(parent, from_=0, to=32, textvariable=self.face_value, width=8).pack(anchor="w")
        ttk.Label(parent, text="Edit regions").pack(anchor="w", pady=(8, 0))
        self.regions = tk.Listbox(parent, selectmode="extended", height=8, exportselection=False)
        for region in FacePart:
            self.regions.insert("end", region.value)
        self.regions.selection_set(0)
        self.regions.pack(fill="x")
        self.regions.bind("<<ListboxSelect>>", lambda _event: self._draw_preview())
        ttk.Button(parent, text="Reset to automatic mask", command=self._reset_mask).pack(
            fill="x", pady=(4, 2)
        )
        ttk.Label(parent, text="Expression intensity").pack(anchor="w", pady=(8, 0))
        ttk.Scale(parent, from_=0, to=1, variable=self.intensity_value).pack(fill="x")
        ttk.Button(
            parent,
            text="Fine-tune eyes, mouth, brows, blush, tears and gaze…",
            command=self._edit_parameters,
        ).pack(fill="x", pady=(4, 0))
        ttk.Label(parent, text="Natural-language instruction (optional)").pack(
            anchor="w", pady=(8, 0)
        )
        self.instruction = tk.Text(parent, height=3, wrap="word")
        self.instruction.pack(fill="x")
        backend_names = tuple(self.commander.send("available_backends"))
        self.backend_value.set(backend_names[0] if backend_names else "")
        ttk.Label(parent, text="Local inpaint backend").pack(anchor="w", pady=(8, 0))
        self.backend_combo = ttk.Combobox(
            parent, state="readonly", textvariable=self.backend_value, values=backend_names
        )
        self.backend_combo.pack(fill="x")
        settings = ttk.Frame(parent)
        settings.pack(fill="x", pady=6)
        ttk.Label(settings, text="Candidates").pack(side="left")
        ttk.Spinbox(settings, from_=1, to=8, textvariable=self.candidate_count_value, width=4).pack(
            side="left", padx=4
        )
        ttk.Label(settings, text="Seed").pack(side="left", padx=(8, 0))
        ttk.Entry(settings, textvariable=self.seed_value, width=10).pack(side="left", padx=4)
        self.generate_button = ttk.Button(
            parent, text="Generate expression candidates", command=self._generate
        )
        self.generate_button.pack(fill="x", pady=5)
        ttk.Label(parent, text="Ranked candidates").pack(anchor="w", pady=(8, 0))
        self.candidate_list = tk.Listbox(parent, height=6, exportselection=False)
        self.candidate_list.pack(fill="x")
        self.candidate_list.bind("<<ListboxSelect>>", self._select_candidate)
        self.score_label = ttk.Label(
            parent,
            text="Expression accuracy is not scored until a semantic evaluator is configured.",
            wraplength=250,
        )
        self.score_label.pack(anchor="w", pady=4)

    # {
    #   責務: [_path_row: add one read-only path and browse control]
    #   処理: [pack a path entry beside a directory/file selector button]
    #   引数: [self: window, parent: owner frame, variable: path variable, callback: selection action]
    #   戻り値: []
    # }
    def _path_row(self, parent, variable, callback) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="…", width=3, command=callback).pack(side="left")

    # {
    #   責務: [_choose_source: select and load one safe source image]
    #   処理: [select a file, bound file bytes, normalize EXIF orientation and refresh preview]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _choose_source(self) -> None:
        selected = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")]
        )
        if not selected:
            return
        path = Path(selected)
        if (
            not path.is_absolute()
            or path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 64 * 1024 * 1024
        ):
            messagebox.showerror(
                "Invalid image", "Choose a regular image file smaller than 64 MiB."
            )
            return
        try:
            content = path.read_bytes()
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > 80_000_000:
                    raise ValueError("Image exceeds 80 megapixels.")
                image.load()
                self.source_image = ImageOps.exif_transpose(image).convert("RGB")
        except (OSError, ValueError) as error:
            messagebox.showerror("Invalid image", str(error))
            return
        self.source_path = path
        self.source_bytes = content
        self.input_value.set(str(path))
        self.analysis = None
        self.result = None
        self.manual_mask = None
        self.mask_edited = False
        self.candidate_list.delete(0, "end")
        self.status_value.set(
            "Image loaded. Analyze faces to choose the target face and preview the automatic mask."
        )
        self._draw_preview()

    # {
    #   責務: [_edit_parameters: edit optional facial-muscle controls]
    #   処理: [open the typed control dialog and retain validated values for the next request]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _edit_parameters(self) -> None:
        parameters = ExpressionControlsDialog(self.root, self.parameters).show()
        if parameters is not None:
            self.parameters = parameters

    # {
    #   責務: [_choose_output: select an output workspace]
    #   処理: [ask for an existing or new output directory]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _choose_output(self) -> None:
        selected = filedialog.askdirectory(mustexist=False)
        if selected:
            self.output_value.set(selected)

    # {
    #   責務: [_analyze: detect faces and populate a stable selection list]
    #   処理: [send normalized source to Process and report detector limitations]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _analyze(self) -> None:
        if self.source_bytes is None:
            messagebox.showinfo("Image required", "Open a source image first.")
            return
        try:
            self.analysis = self.commander.send("analyze", self.source_bytes)
        except Exception as error:
            messagebox.showerror("Face analysis failed", str(error))
            return
        self.manual_mask = None
        self.mask_edited = False
        if self.analysis.faces:
            self.face_value.set(min(self.face_value.get(), len(self.analysis.faces) - 1))
            self.status_value.set(
                f"Detected {len(self.analysis.faces)} face(s). " + " ".join(self.analysis.warnings)
            )
        else:
            self.status_value.set(
                "No frontal face was detected. Try a clearer, front-facing image."
            )
        self._draw_preview()

    # {
    #   責務: [_selected_parts: return the user's unique region selection]
    #   処理: [map selected listbox IDs to typed FacePart values]
    #   引数: [self: window]
    #   戻り値: [tuple[FacePart, ...]: selected edit regions]
    # }
    def _selected_parts(self) -> tuple[FacePart, ...]:
        return tuple(FacePart(self.regions.get(index)) for index in self.regions.curselection())

    # {
    #   責務: [_automatic_mask: create the current estimated face-region mask]
    #   処理: [resolve selected face and regions through the shared Data endpoint]
    #   引数: [self: window]
    #   戻り値: [Image.Image | None: preview mask]
    # }
    def _automatic_mask(self) -> Image.Image | None:
        if not self.analysis or not self.analysis.faces or self.source_image is None:
            return None
        face_index = self.face_value.get()
        if not 0 <= face_index < len(self.analysis.faces):
            return None
        parts = self._selected_parts()
        if not parts:
            return None
        mask_bytes = self.commander.send("preview_mask", self.analysis, face_index, parts)
        with Image.open(io.BytesIO(mask_bytes)) as image:
            image.load()
            return image.convert("L")

    # {
    #   責務: [_draw_preview: display source/candidate and mask overlay at a bounded canvas size]
    #   処理: [fit the image, overlay mask and face boxes, retain scale and offsets for mouse mapping]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _draw_preview(self) -> None:
        if self.source_image is None:
            self.canvas.delete("all")
            self.canvas.create_text(30, 30, anchor="nw", text="Open an image", fill="white")
            return
        preview = self.source_image.copy()
        candidate = self._selected_candidate_path()
        if candidate is not None and self.output_value.get():
            try:
                with Image.open(Path(self.output_value.get()) / candidate.image_path) as image:
                    preview = image.convert("RGB")
            except OSError:
                pass
        mask = self.manual_mask if self.mask_edited and self.manual_mask else self._automatic_mask()
        if mask is not None and mask.size == preview.size:
            overlay = Image.new("RGBA", preview.size, (255, 30, 50, 0))
            alpha = mask.point(lambda value: round(value * 0.38))
            overlay.putalpha(alpha)
            preview = Image.alpha_composite(preview.convert("RGBA"), overlay).convert("RGB")
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        width, height = max(width, 100), max(height, 100)
        self._scale = min((width - 20) / preview.width, (height - 20) / preview.height)
        rendered = preview.resize(
            (
                max(1, round(preview.width * self._scale)),
                max(1, round(preview.height * self._scale)),
            ),
            Image.Resampling.LANCZOS,
        )
        self._offset = ((width - rendered.width) // 2, (height - rendered.height) // 2)
        self._preview_photo = ImageTk.PhotoImage(rendered)
        self.canvas.delete("all")
        self.canvas.create_image(*self._offset, anchor="nw", image=self._preview_photo)
        self._draw_face_boxes()

    # {
    #   責務: [_draw_face_boxes: draw targetable face boxes over the image preview]
    #   処理: [convert normalized face boxes through preview scale/offset]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _draw_face_boxes(self) -> None:
        if not self.analysis or not self.source_image:
            return
        ox, oy = self._offset
        for face in self.analysis.faces:
            x, y, width, height = face.bbox
            bounds = (
                ox + x * self.source_image.width * self._scale,
                oy + y * self.source_image.height * self._scale,
                ox + (x + width) * self.source_image.width * self._scale,
                oy + (y + height) * self.source_image.height * self._scale,
            )
            color = "#00ff80" if face.index == self.face_value.get() else "#ffd34d"
            self.canvas.create_rectangle(*bounds, outline=color, width=2)
            self.canvas.create_text(
                bounds[0] + 4, bounds[1] + 2, text=f"Face {face.index}", anchor="nw", fill=color
            )

    # {
    #   責務: [_image_coordinates: map canvas coordinates into source image pixels]
    #   処理: [subtract centered preview offset, divide by preview scale, clamp to source bounds]
    #   引数: [self: window, event: Tk pointer event]
    #   戻り値: [tuple[int, int] | None: source pixel location]
    # }
    def _image_coordinates(self, event) -> tuple[int, int] | None:
        if self.source_image is None:
            return None
        x = round((event.x - self._offset[0]) / self._scale)
        y = round((event.y - self._offset[1]) / self._scale)
        if not 0 <= x < self.source_image.width or not 0 <= y < self.source_image.height:
            return None
        return x, y

    # {
    #   責務: [_begin_paint: start manual mask painting or erasing]
    #   処理: [copy the automatic region mask as the initial refinement layer]
    #   引数: [self: window, event: Tk pointer event]
    #   戻り値: []
    # }
    def _begin_paint(self, event) -> None:
        if self.source_image is None:
            return
        base = self.manual_mask if self.mask_edited and self.manual_mask else self._automatic_mask()
        if base is None:
            messagebox.showinfo("Select region", "Analyze a face and select an edit region first.")
            return
        self.manual_mask = base.copy()
        self.mask_edited = True
        self._painting = True
        self._paint(event, 255 if event.num == 1 else 0)

    # {
    #   責務: [_paint: add or erase a round brush stroke on the manual mask]
    #   処理: [map pointer coordinates to source pixels and draw a scaled brush stroke]
    #   引数: [self: window, event: pointer position, value: 0/255 mask value]
    #   戻り値: []
    # }
    def _paint(self, event, value: int) -> None:
        if not self._painting or self.manual_mask is None:
            return
        point = self._image_coordinates(event)
        if point is None:
            return
        radius = max(3, round(min(self.manual_mask.size) * 0.012))
        x, y = point
        ImageDraw.Draw(self.manual_mask).ellipse(
            (x - radius, y - radius, x + radius, y + radius), fill=value
        )
        self._draw_preview()

    # {
    #   責務: [_end_paint: finish a manual mask stroke]
    #   処理: [clear pointer-drag state and refresh status]
    #   引数: [self: window, _event: Tk pointer event]
    #   戻り値: []
    # }
    def _end_paint(self, _event) -> None:
        self._painting = False
        if self.mask_edited:
            self.status_value.set(
                "Manual mask updated. Paint white to include pixels; erase black to preserve them."
            )

    # {
    #   責務: [_reset_mask: discard manual strokes and restore detector regions]
    #   処理: [clear manual mask and refresh automatic preview]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _reset_mask(self) -> None:
        self.manual_mask = None
        self.mask_edited = False
        self._draw_preview()

    # {
    #   責務: [_generate: validate and submit an expression candidate batch]
    #   処理: [create structured request and run generation on a worker thread]
    #   引数: [self: window]
    #   戻り値: []
    # }
    def _generate(self) -> None:
        if self.source_bytes is None or self.source_image is None:
            messagebox.showinfo("Image required", "Open and analyze an image first.")
            return
        if not self.analysis or not self.analysis.faces:
            messagebox.showinfo("Face required", "No face is available for editing.")
            return
        workspace = self.output_value.get().strip()
        backend = self.backend_value.get().strip()
        if not workspace or not backend:
            messagebox.showinfo(
                "Settings required", "Choose an output folder and configure an inpaint backend."
            )
            return
        try:
            seed_text = self.seed_value.get().strip()
            seed = int(seed_text) if seed_text else None
            request = ExpressionEditRequest(
                self.source_bytes,
                ExpressionPreset(self.target_value.get()),
                intensity=float(self.intensity_value.get()),
                mode=ExpressionMode(self.mode_value.get()),
                face_index=self.face_value.get(),
                edit_regions=self._selected_parts(),
                parameters=self.parameters,
                natural_language=self.instruction.get("1.0", "end-1c").strip(),
                candidate_count=int(self.candidate_count_value.get()),
                seed=seed,
                manual_mask=self._encode_manual_mask() if self.mask_edited else None,
            )
        except (ValueError, TypeError) as error:
            messagebox.showerror("Invalid request", str(error))
            return
        self._busy = True
        self.generate_button.configure(state="disabled")
        self.status_value.set("Generating masked candidates…")
        thread = threading.Thread(
            target=self._run_generation,
            args=(request, workspace, backend),
            daemon=True,
        )
        thread.start()

    # {
    #   責務: [_encode_manual_mask: encode a refined grayscale mask]
    #   処理: [serialize the source-sized mask as lossless PNG]
    #   引数: [self: window]
    #   戻り値: [bytes | None: manual mask]
    # }
    def _encode_manual_mask(self) -> bytes | None:
        if self.manual_mask is None:
            return None
        output = io.BytesIO()
        self.manual_mask.save(output, format="PNG", optimize=True)
        return output.getvalue()

    # {
    #   責務: [_run_generation: execute one retouch request outside Tk event handling]
    #   処理: [call Process and schedule success/error update on the Tk thread]
    #   引数: [self: window, request: structured edit, workspace: output folder, backend: preferred model]
    #   戻り値: []
    # }
    def _run_generation(self, request, workspace: str, backend: str) -> None:
        try:
            result = self.commander.send("retouch", request, workspace, backend)
        except Exception as error:
            self.root.after(0, self._generation_failed, str(error))
            return
        self.root.after(0, self._generation_succeeded, result)

    # {
    #   責務: [_generation_failed: report backend errors and re-enable the editor]
    #   処理: [update status, show one actionable error, restore button state]
    #   引数: [self: window, message: failed operation detail]
    #   戻り値: []
    # }
    def _generation_failed(self, message: str) -> None:
        self._busy = False
        self.generate_button.configure(state="normal")
        self.status_value.set("Generation failed. Source and prior candidates remain unchanged.")
        messagebox.showerror("Expression edit failed", message)

    # {
    #   責務: [_generation_succeeded: render saved candidate scores and outputs]
    #   処理: [fill ranked list, show selected candidate and warnings, re-enable editor]
    #   引数: [self: window, result: persisted retouch result]
    #   戻り値: []
    # }
    def _generation_succeeded(self, result) -> None:
        self._busy = False
        self.generate_button.configure(state="normal")
        self.result = result
        self.candidate_list.delete(0, "end")
        for index, candidate in enumerate(result.candidates):
            score = candidate.evaluation.ranking_score
            self.candidate_list.insert(
                "end",
                f"#{index + 1} {candidate.backend_id}  preservation {score:.3f}  seed {candidate.seed}",
            )
        if result.candidates:
            self.candidate_list.selection_set(result.selected_candidate)
        self.score_label.configure(
            text="Semantic expression score unavailable; candidate ranking uses measured preservation/locality proxies."
        )
        self.status_value.set(
            "Saved " + str(len(result.candidates)) + " candidate(s). " + " ".join(result.warnings)
        )
        self._draw_preview()

    # {
    #   責務: [_selected_candidate_path: return the selected candidate metadata]
    #   処理: [resolve current ranked candidate index]
    #   引数: [self: window]
    #   戻り値: [ExpressionCandidate | None: selected image record]
    # }
    def _selected_candidate_path(self):
        if self.result is None:
            return None
        selection = self.candidate_list.curselection()
        if not selection:
            return self.result.candidates[self.result.selected_candidate]
        return self.result.candidates[selection[0]]

    # {
    #   責務: [_select_candidate: switch preview to one ranked candidate]
    #   処理: [refresh selected candidate display and score metadata]
    #   引数: [self: window, _event: list selection]
    #   戻り値: []
    # }
    def _select_candidate(self, _event) -> None:
        candidate = self._selected_candidate_path()
        if candidate:
            self.score_label.configure(
                text=(
                    f"Expression match: {candidate.evaluation.expression_match if candidate.evaluation.expression_match is not None else 'not evaluated'}\n"
                    f"Identity proxy: {candidate.evaluation.identity_preservation:.3f}  "
                    f"Non-target: {candidate.evaluation.non_target_preservation:.3f}  "
                    f"Locality: {candidate.evaluation.locality:.3f}\n"
                    f"History: {candidate.manifest_path}"
                )
            )
        self._draw_preview()


# {
#   責務: [launch: create and display the Expression Retouch editor]
#   処理: [construct Tk, bind commander and enter the application loop]
#   引数: [commander: UI-facing command boundary]
#   戻り値: []
# }
def launch(commander: ExpressionRetouchUiCommander) -> None:
    root = tk.Tk()
    ExpressionRetouchWindow(root, commander)
    root.mainloop()
