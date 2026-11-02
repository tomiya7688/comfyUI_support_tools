"""Tk interface for choosing Text, Image, and Retouch pixel-art workflows."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from comfyui_support_tools.shared.pixel_art import (
    SIZE_PRESETS,
    PixelArtApplication,
    PixelArtRequest,
    PixelArtSettings,
    PixelEdit,
    PixelTextBackend,
    load_palette,
    nearest_preview,
)

from .pixel_cleanup_review import PixelCleanupReviewDialog


# {
# 責務: [ImageConversionActions: implement batch and candidate image workflows]
# フィールド: [source_path, application, settings controls, preview callback]
# 処理: [keep image conversion UI behavior separate from root window setup]
# }
class ImageConversionActions:
    # {
    # 責務: [compare_image_modes: compare four structure/palette conversion candidates]
    # 処理: [show native-grid candidates and accept one result into the editor project]
    # 引数: [None: reads selected source image and conversion settings]
    # 戻り値: [None: opens comparison dialog or reports missing input]
    # }
    def compare_image_modes(self) -> None:
        if self.source_path is None:
            messagebox.showinfo("Compare modes", "Open a source image first.", parent=self)
            return
        try:
            with Image.open(self.source_path) as image:
                candidates = self.application.image_to_pixel_candidates(
                    image.copy(), self._settings()
                )
        except (OSError, ValueError) as error:
            messagebox.showerror("Compare modes", str(error), parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Image-to-pixel candidates")
        dialog.transient(self)
        dialog.geometry("520x520")
        selected = tk.IntVar(dialog, value=0)
        details = tk.StringVar(dialog)
        canvas = tk.Canvas(dialog, background="#ececec", height=360)
        canvas.pack(fill="both", expand=True, padx=12, pady=8)
        image_reference = {"photo": None}

        # {
        # 責務: [show_mode: render a candidate and its metric comparison]
        # 処理: [update crisp preview and native-size quality proxy]
        # 引数: [_args: optional Tk variable trace values]
        # 戻り値: [None: refreshes comparison widgets]
        # }
        def show_mode(*_args):
            mode, result = candidates[selected.get()]
            scale = next(
                (
                    value
                    for value in (8, 4, 1)
                    if max(result.grid.width, result.grid.height) * value <= 480
                ),
                1,
            )
            image_reference["photo"] = ImageTk.PhotoImage(nearest_preview(result.grid, scale))
            canvas.delete("all")
            canvas.create_image(8, 8, image=image_reference["photo"], anchor="nw")
            details.set(
                f"{mode}: {dict(result.metric.counts)['color_count']} colors; "
                f"{result.metadata['changed_pixels']} changed pixels vs faithful; "
                f"score proxy {result.metric.score:.3f}"
            )

        for index, (mode, _result) in enumerate(candidates):
            ttk.Radiobutton(
                dialog,
                text=mode.replace("_", " ").title(),
                value=index,
                variable=selected,
                command=show_mode,
            ).pack(anchor="w", padx=12)
        ttk.Label(dialog, textvariable=details).pack(anchor="w", padx=12)

        # {
        # 責務: [accept_mode: add the selected conversion to the editor]
        # 処理: [create a fresh undoable project from the reviewed result]
        # 引数: [None: reads current candidate selection]
        # 戻り値: [None: closes dialog after accepting]
        # }
        def accept_mode():
            self._set_result(candidates[selected.get()][1])
            dialog.destroy()

        ttk.Button(dialog, text="Use candidate", command=accept_mode).pack(
            anchor="e", padx=12, pady=10
        )
        show_mode()

    # {
    # 責務: [convert_batch: run faithful folder conversion with optional recursion]
    # 処理: [select source/output folders and write collision-safe outputs plus manifest]
    # 引数: [None: reads image mode and pixel settings from controls]
    # 戻り値: [None: reports manifest path or conversion error]
    # }
    def convert_batch(self) -> None:
        source = filedialog.askdirectory(title="Select source image folder")
        if not source:
            return
        destination = filedialog.askdirectory(title="Select output folder")
        if not destination:
            return
        recursive = messagebox.askyesno("Batch conversion", "Include subfolders?", parent=self)
        try:
            manifest = self.application.batch_image_to_pixel(
                Path(source),
                Path(destination),
                self._settings(),
                recursive=recursive,
                mode=self.image_mode.get(),
            )
            self.status.set(f"Batch complete; manifest: {manifest.name}")
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("Batch conversion", str(error), parent=self)


# {
# 責務: [PixelRetouchActions: implement reversible pixel-grid editor actions]
# フィールド: [project, result, canvas, zoom, brush, editor tool]
# 処理: [isolate manual edits and cleanup review from application bootstrap]
# }
class PixelRetouchActions:
    # {
    # 責務: [finish_shape: commit a line or filled rectangle on mouse release]
    # 処理: [convert drag endpoints into one undoable native-grid operation]
    # 引数: [event: Tk canvas release event]
    # 戻り値: [None: updates active retouch state]
    # }
    def finish_shape(self, event) -> None:
        start = getattr(self, "_drag_start", None)
        if start is None or self.project is None or self.editor_tool not in {"line", "rectangle"}:
            return
        self._drag_start = None
        scale = int(self.zoom.get().removesuffix("x"))
        end = (
            int((self.canvas.canvasx(event.x) - 12) // scale),
            int((self.canvas.canvasy(event.y) - 12) // scale),
        )
        try:
            self.project.apply(
                (
                    PixelEdit(
                        self.editor_tool,
                        *start,
                        _hex_rgba(self.color.get()),
                        end_x=end[0],
                        end_y=end[1],
                    ),
                )
            )
            self.result = self.application.retouch(self.project.grid, ())
            self._render()
        except ValueError as error:
            self.status.set(str(error))

    # {
    # 責務: [mirror_grid: mirror the active sprite horizontally]
    # 処理: [append deterministic mirror edit to undoable project history]
    # 引数: [None: uses active retouch project]
    # 戻り値: [None: refreshes preview or prompts for an image]
    # }
    def mirror_grid(self) -> None:
        if self.project is None:
            return
        self.project.apply((PixelEdit("mirror_horizontal"),))
        self.result = self.application.retouch(self.project.grid, ())
        self._render()

    # {
    # 責務: [replace_color: replace a selected palette entry with the brush color]
    # 処理: [ask for source color and commit exact RGBA palette substitution]
    # 引数: [None: reads active project and current brush color]
    # 戻り値: [None: updates preview or leaves project unchanged]
    # }
    def replace_color(self) -> None:
        if self.project is None:
            return
        source = simpledialog.askstring(
            "Replace palette color", "Source color (#RRGGBB):", parent=self
        )
        if source is None:
            return
        try:
            old = _hex_rgba(source)
            new = _hex_rgba(self.color.get())
            result = self.application.replace_palette_color(self.project.grid, old, new)
            self.project.apply_grid(result.grid)
            self.result = self.application.retouch(self.project.grid, ())
            self._render()
        except ValueError as error:
            messagebox.showerror("Palette replacement", str(error), parent=self)

    # {
    # 責務: [reduce_palette: apply the selected maximum palette size to the active grid]
    # 処理: [quantize a candidate and commit it as one undoable operation]
    # 引数: [None: reads the selected color count]
    # 戻り値: [None: updates the active preview or reports invalid settings]
    # }
    def reduce_palette(self) -> None:
        if self.project is None:
            return
        try:
            result = self.application.reduce_palette(self.project.grid, int(self.colors.get()))
            self.project.apply_grid(result.grid)
            self.result = self.application.retouch(self.project.grid, ())
            self._render()
        except (ValueError, RuntimeError) as error:
            messagebox.showerror("Palette reduction", str(error), parent=self)

    # {
    # 責務: [clean_alpha: remove partial alpha at sprite edges]
    # 処理: [use a transparent/opaque threshold and save the change in undo history]
    # 引数: [None: uses active retouch grid]
    # 戻り値: [None: refreshes the edited preview]
    # }
    def clean_alpha(self) -> None:
        if self.project is None:
            return
        try:
            result = self.application.cleanup_transparent_edges(self.project.grid)
            self.project.apply_grid(result.grid)
            self.result = self.application.retouch(self.project.grid, ())
            self._render()
        except ValueError as error:
            messagebox.showerror("Alpha cleanup", str(error), parent=self)

    # {
    # 責務: [review_cleanup: compare conservative cleanup candidates before applying]
    # 処理: [show pixel diffs and let the user accept one candidate into undo history]
    # 引数: [None: uses the active retouch project]
    # 戻り値: [None: opens review dialog or reports missing source]
    # }
    def review_cleanup(self) -> None:
        if self.workflow.get() != "Retouch" or self.project is None:
            messagebox.showinfo(
                "Pixel cleanup", "Open an image and select Retouch first.", parent=self
            )
            return
        PixelCleanupReviewDialog(
            self,
            self.application,
            self.project,
            on_accept=self._accept_cleanup_grid,
        )

    # {
    # 責務: [_accept_cleanup_grid: commit a reviewed pixel cleanup into project history]
    # 処理: [append accepted candidate and refresh the main canvas]
    # 引数: [grid: selected cleanup candidate]
    # 戻り値: [None: project and preview updated]
    # }
    def _accept_cleanup_grid(self, grid) -> None:
        if self.project is None:
            return
        self.project.apply_grid(grid)
        self.result = self.application.retouch(self.project.grid, ())
        self._render()


# {
# 責務: [PixelArtWindow: standalone UI for all Pixel Art Creator entry workflows]
# フィールド: [workflow/settings controls, preview canvas, project and shared application]
# 処理: [allow text/image/retouch selection from one pixel-focused window]
# }
class PixelArtWindow(ImageConversionActions, PixelRetouchActions, tk.Tk):
    # {
    # 責務: [__init__: create the pixel art desktop application window]
    # 処理: [wire common controls, editor canvas, and injected generation backend]
    # 引数: [text_backend: optional Text workflow adapter]
    # 戻り値: [None: initialized Tk application]
    # }
    def __init__(self, text_backend: PixelTextBackend | None = None):
        super().__init__()
        self.title("Pixel Art Creator")
        self.geometry("1050x760")
        self.minsize(760, 560)
        self.application = PixelArtApplication(text_backend)
        self.result = None
        self.project = None
        self.palette = ()
        self._preview_photo = None
        self.workflow = tk.StringVar(self, value="Image")
        self.size = tk.StringVar(self, value="64")
        self.colors = tk.StringVar(self, value="16")
        self.palette_mode = tk.StringVar(self, value="count")
        self.zoom = tk.StringVar(self, value="8x")
        self.image_mode = tk.StringVar(self, value="faithful")
        self.crop_policy = tk.StringVar(self, value="fit")
        self.dithering = tk.StringVar(self, value="none")
        self.category = tk.StringVar(self, value="character")
        self.prompt = tk.StringVar(self)
        self.color = tk.StringVar(self, value="#202020")
        self.show_grid = tk.BooleanVar(self, value=True)
        self.status = tk.StringVar(self, value="Text / Image / Retouchを選択してください。")
        self._build()

    # {
    # 責務: [_build: layout shared settings and crisp pixel canvas]
    # 処理: [provide three workflow choices, pixel settings, import, edit, and export actions]
    # 引数: [None: uses initialized Tk variables]
    # 戻り値: [None: updates UI layout]
    # }
    def _build(self) -> None:
        self._build_settings()
        self._build_workflow_actions()
        self._build_editor_actions()
        self._build_canvas()
        ttk.Label(self, textvariable=self.status, padding=8).pack(fill="x")
        self.editor_tool = "pencil"
        self.source_path = None

    # {
    # 責務: [_build_settings: lay out pixel dimensions, palette, crop, and preview settings]
    # 処理: [create shared settings controls in two compact rows]
    # 引数: [None: reads Tk variables initialized by the window]
    # 戻り値: [None: attaches settings controls]
    # }
    def _build_settings(self) -> None:
        controls = ttk.Frame(self, padding=10)
        controls.pack(fill="x")
        self._combo(controls, "Workflow", self.workflow, ("Text", "Image", "Retouch"), 0)
        self._combo(controls, "Grid", self.size, tuple(str(size) for size in SIZE_PRESETS), 1)
        self._combo(
            controls,
            "Colors",
            self.colors,
            tuple(str(size) for size in (4, 8, 16, 32, 64, 128, 256)),
            2,
        )
        self._combo(
            controls,
            "Palette",
            self.palette_mode,
            ("auto", "count", "unlimited", "monochrome", "custom"),
            3,
        )
        self._combo(
            controls,
            "Category",
            self.category,
            (
                "character",
                "monster",
                "portrait",
                "face_icon",
                "item",
                "equipment",
                "effect",
                "ui_icon",
                "background",
                "tile",
            ),
            4,
        )
        self._combo(controls, "Preview", self.zoom, ("1x", "4x", "8x", "16x", "32x"), 5)
        self._combo(
            controls,
            "Image mode",
            self.image_mode,
            ("faithful", "simplified", "sprite", "icon", "palette_constrained"),
            0,
            row=1,
        )
        self._combo(
            controls,
            "Crop",
            self.crop_policy,
            ("fit", "center_crop", "smart", "transparent_pad"),
            1,
            row=1,
        )
        self._combo(
            controls,
            "Dither",
            self.dithering,
            ("none", "ordered", "floyd_steinberg"),
            2,
            row=1,
        )

    # {
    # 責務: [_build_workflow_actions: add source, palette, convert, batch, and comparison controls]
    # 処理: [connect user workflow actions to window callbacks]
    # 引数: [None: uses initialized workflow variables]
    # 戻り値: [None: attaches workflow command row]
    # }
    def _build_workflow_actions(self) -> None:
        prompt_row = ttk.Frame(self, padding=(10, 0, 10, 8))
        prompt_row.pack(fill="x")
        ttk.Label(prompt_row, text="Prompt").pack(side="left")
        ttk.Entry(prompt_row, textvariable=self.prompt).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(prompt_row, text="Open image", command=self.open_image).pack(side="left")
        ttk.Button(prompt_row, text="Palette…", command=self.open_palette).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(prompt_row, text="Create / Convert", command=self.run_workflow).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(prompt_row, text="Batch folder…", command=self.convert_batch).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(prompt_row, text="Compare modes…", command=self.compare_image_modes).pack(
            side="left", padx=(6, 0)
        )

    # {
    # 責務: [_build_editor_actions: create manual, cleanup, history, and export controls]
    # 処理: [connect pixel-grid operations and project actions to callbacks]
    # 引数: [None: uses current retouch state and Tk variables]
    # 戻り値: [None: attaches editor command row]
    # }
    def _build_editor_actions(self) -> None:
        tools = ttk.Frame(self, padding=(10, 0, 10, 8))
        tools.pack(fill="x")
        ttk.Label(tools, text="Brush color").pack(side="left")
        ttk.Entry(tools, textvariable=self.color, width=10).pack(side="left", padx=6)
        for label, action in (("Pencil", "pencil"), ("Erase", "eraser"), ("Fill", "fill")):
            ttk.Button(
                tools, text=label, command=lambda selected=action: self.set_editor_tool(selected)
            ).pack(side="left", padx=2)
        for label, action in (("Line", "line"), ("Rectangle", "rectangle")):
            ttk.Button(
                tools, text=label, command=lambda selected=action: self.set_editor_tool(selected)
            ).pack(side="left", padx=2)
        ttk.Button(tools, text="Mirror", command=self.mirror_grid).pack(side="left", padx=2)
        ttk.Button(tools, text="Replace color…", command=self.replace_color).pack(
            side="left", padx=2
        )
        ttk.Button(tools, text="Undo", command=self.undo).pack(side="left", padx=(12, 2))
        ttk.Button(tools, text="Redo", command=self.redo).pack(side="left", padx=2)
        ttk.Button(tools, text="Review cleanup…", command=self.review_cleanup).pack(
            side="left", padx=2
        )
        ttk.Button(tools, text="Reduce palette", command=self.reduce_palette).pack(
            side="left", padx=2
        )
        ttk.Button(tools, text="Clean alpha", command=self.clean_alpha).pack(side="left", padx=2)
        ttk.Checkbutton(tools, text="Grid", variable=self.show_grid, command=self._render).pack(
            side="left", padx=6
        )
        ttk.Button(tools, text="Save project", command=self.save_project).pack(
            side="left", padx=(10, 2)
        )
        ttk.Button(tools, text="Load project", command=self.load_project).pack(side="left", padx=2)
        ttk.Button(tools, text="Export PNG + metadata", command=self.export).pack(side="right")

    # {
    # 責務: [_build_canvas: create the scrollable nearest-neighbor pixel editing canvas]
    # 処理: [wire mouse edit events, grid toggle, and zoom refresh]
    # 引数: [None: no inputs]
    # 戻り値: [None: attaches preview canvas and status label]
    # }
    def _build_canvas(self) -> None:
        preview_frame = ttk.Frame(self, padding=(10, 0, 10, 0))
        preview_frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(preview_frame, background="#ececec", highlightthickness=0)
        vertical = ttk.Scrollbar(preview_frame, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        self.canvas.bind("<Button-1>", self.edit_pixel)
        self.canvas.bind("<B1-Motion>", self.edit_pixel)
        self.canvas.bind("<ButtonRelease-1>", self.finish_shape)
        self.zoom.trace_add("write", lambda *_args: self._render())

    # {
    # 責務: [_combo: add a labeled readonly shared setting control]
    # 処理: [place combobox in settings row]
    # 引数: [parent: control frame, label: visible setting, variable/values: selection state]
    # 戻り値: [None: control is packed]
    # }
    def _combo(self, parent, label, variable, values, index, row=0):
        group = ttk.Frame(parent)
        group.grid(row=row, column=index, sticky="w", padx=(0, 8))
        ttk.Label(group, text=label).pack(anchor="w")
        ttk.Combobox(group, textvariable=variable, values=values, state="readonly", width=13).pack(
            anchor="w"
        )

    # {
    # 責務: [open_image: select and load artwork for image conversion or retouch]
    # 処理: [keep source path and prepare a strict-grid candidate]
    # 引数: [None: obtains path from file dialog]
    # 戻り値: [None: updates current preview or status]
    # }
    def open_image(self) -> None:
        selected = filedialog.askopenfilename(
            filetypes=(("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*"))
        )
        if not selected:
            return
        try:
            self.source_path = Path(selected)
            with Image.open(self.source_path) as image:
                self._set_result(self.application.image_to_pixel(image.copy(), self._settings()))
            self.status.set(
                f"Loaded {self.source_path.name}; select Retouch to edit individual cells."
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("Image error", str(error), parent=self)

    # {
    # 責務: [open_palette: load a shared RGBA color palette]
    # 処理: [parse palette JSON and switch common palette mode to custom]
    # 引数: [None: obtains path from file dialog]
    # 戻り値: [None: updates palette state]
    # }
    def open_palette(self) -> None:
        selected = filedialog.askopenfilename(filetypes=(("Palette JSON", "*.json"),))
        if selected:
            try:
                self.palette = load_palette(Path(selected))
                self.palette_mode.set("custom")
                self.status.set(f"Loaded {len(self.palette)} palette colors.")
            except (OSError, ValueError) as error:
                messagebox.showerror("Palette error", str(error), parent=self)

    # {
    # 責務: [_settings: read and validate one shared workflow settings object]
    # 処理: [combine grid/category/palette selections into reusable settings]
    # 引数: [None: reads Tk variables]
    # 戻り値: [PixelArtSettings: validated common configuration]
    # }
    def _settings(self) -> PixelArtSettings:
        return PixelArtSettings(
            size=int(self.size.get()),
            category=self.category.get(),
            palette_mode=self.palette_mode.get(),
            color_count=int(self.colors.get()),
            palette=self.palette,
            transparent=True,
            crop_policy=self.crop_policy.get(),
            dithering=self.dithering.get(),
            preview_scale=int(self.zoom.get().removesuffix("x")),
        )

    # {
    # 責務: [run_workflow: execute the selected Text/Image/Retouch entry]
    # 処理: [route prompt candidates or an imported source image through shared processing]
    # 引数: [None: reads UI values]
    # 戻り値: [None: displays result or user-facing validation error]
    # }
    def run_workflow(self) -> None:
        try:
            settings = self._settings()
            mode = self.workflow.get()
            if mode == "Text":
                request = PixelArtRequest(self.prompt.get(), settings, candidate_count=4)
                candidates = self.application.text_to_pixel(request)
                self._set_result(candidates[0])
                self.status.set(
                    f"Ranked {len(candidates)} text candidates; top deterministic score {candidates[0].metric.score:.3f}."
                )
            elif mode == "Retouch":
                if self.project is None:
                    raise ValueError("Open an image or load a project before retouching.")
                self.result = self.application.retouch(self.project.grid, ())
                self._render()
                self.status.set("Retouching the current pixel project; undo history is preserved.")
            elif self.source_path is None:
                raise ValueError("Open a source image first for Image mode.")
            else:
                with Image.open(self.source_path) as image:
                    self._set_result(
                        self.application.image_to_pixel(
                            image.copy(), settings, self.image_mode.get()
                        )
                    )
                self.status.set("Converted on the shared strict pixel grid.")
        except (OSError, ValueError, RuntimeError) as error:
            messagebox.showerror("Pixel Art Creator", str(error), parent=self)

    # {
    # 責務: [_set_result: attach a new immutable image result to editor state]
    # 処理: [create undo history and refresh nearest-neighbor preview]
    # 引数: [result: shared pipeline result]
    # 戻り値: [None: stores and renders result]
    # }
    def _set_result(self, result) -> None:
        self.result = result
        self.project = self.application.new_project(result)
        self._render()

    # {
    # 責務: [_render: show a crisp scaled preview and native-size metrics]
    # 処理: [use nearest-neighbor scale and retain ImageTk reference]
    # 引数: [None: renders current result]
    # 戻り値: [None: updates preview canvas]
    # }
    def _render(self) -> None:
        if self.project is None:
            return
        scale = int(self.zoom.get().removesuffix("x"))
        preview = nearest_preview(self.project.grid, scale)
        self._preview_photo = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        self.canvas.create_image(12, 12, image=self._preview_photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, preview.width + 24, preview.height + 24))
        if self.show_grid.get() and scale >= 4:
            width, height = self.project.grid.width, self.project.grid.height
            for x in range(width + 1):
                edge = 12 + x * scale
                self.canvas.create_line(
                    edge, 12, edge, 12 + height * scale, fill="#777777", width=1
                )
            for y in range(height + 1):
                edge = 12 + y * scale
                self.canvas.create_line(12, edge, 12 + width * scale, edge, fill="#777777", width=1)
        metric = self.result.metric
        self.status.set(
            f"{self.project.grid.width}×{self.project.grid.height} | {dict(metric.counts).get('color_count', 0)} colors | score proxy {metric.score:.3f}"
        )

    # {
    # 責務: [set_editor_tool: select pencil/eraser/fill editor operation]
    # 処理: [store active mouse editing mode]
    # 引数: [tool: editing operation name]
    # 戻り値: [None: updates active tool]
    # }
    def set_editor_tool(self, tool: str) -> None:
        self.editor_tool = tool
        self._drag_start = None

    # {
    # 責務: [edit_pixel: map canvas mouse position to one native pixel cell]
    # 処理: [convert zoomed coordinates and append reversible project edit]
    # 引数: [event: Tk canvas mouse event]
    # 戻り値: [None: updates current retouch result]
    # }
    def edit_pixel(self, event) -> None:
        if self.workflow.get() != "Retouch" or self.project is None:
            return
        scale = int(self.zoom.get().removesuffix("x"))
        x, y = (
            (self.canvas.canvasx(event.x) - 12) // scale,
            (self.canvas.canvasy(event.y) - 12) // scale,
        )
        try:
            color = _hex_rgba(self.color.get())
            if self.editor_tool in {"line", "rectangle"}:
                if getattr(self, "_drag_start", None) is None:
                    self._drag_start = (int(x), int(y))
                return
            edit = PixelEdit(self.editor_tool, int(x), int(y), color)
            grid = self.project.apply((edit,))
            self.result = self.application.retouch(grid, ())
            self._render()
        except ValueError as error:
            self.status.set(str(error))

    # {
    # 責務: [undo: restore previous pixel edit snapshot]
    # 処理: [move history cursor and rerender]
    # 引数: [None: no inputs]
    # 戻り値: [None: updates editor]
    # }
    def undo(self) -> None:
        if self.project is not None:
            self.project.undo()
            self.result = self.application.retouch(self.project.grid, ())
            self._render()

    # {
    # 責務: [redo: restore next pixel edit snapshot]
    # 処理: [move history cursor and rerender]
    # 引数: [None: no inputs]
    # 戻り値: [None: updates editor]
    # }
    def redo(self) -> None:
        if self.project is not None:
            self.project.redo()
            self.result = self.application.retouch(self.project.grid, ())
            self._render()

    # {
    # 責務: [save_project: persist current grid and edit undo history]
    # 処理: [select a new project directory and save snapshot history]
    # 引数: [None: reads project and path dialog]
    # 戻り値: [None: shows save status or error dialog]
    # }
    def save_project(self) -> None:
        if self.project is None:
            messagebox.showinfo(
                "Pixel Art Creator", "Create or convert an image first.", parent=self
            )
            return
        selected = filedialog.asksaveasfilename(
            title="Save Pixel Art project as folder name", defaultextension=".pixelproj"
        )
        if selected:
            try:
                self.project.save(Path(selected))
                self.status.set(f"Saved project history to {Path(selected).name}.")
            except (OSError, ValueError) as error:
                messagebox.showerror("Project save error", str(error), parent=self)

    # {
    # 責務: [load_project: restore editable grid and persisted undo history]
    # 処理: [load selected project directory without resetting its history]
    # 引数: [None: obtains project directory from dialog]
    # 戻り値: [None: refreshes editor or displays error]
    # }
    def load_project(self) -> None:
        selected = filedialog.askdirectory(title="Open Pixel Art project")
        if selected:
            try:
                from comfyui_support_tools.shared.pixel_art.application import PixelProject

                self.project = PixelProject.load(Path(selected))
                self.result = self.application.retouch(self.project.grid, ())
                self.workflow.set("Retouch")
                self._render()
            except (OSError, ValueError, KeyError) as error:
                messagebox.showerror("Project load error", str(error), parent=self)

    # {
    # 責務: [export: write current lossless pixel PNG and metadata sidecars]
    # 処理: [choose folder and refuse overwrite through application export service]
    # 引数: [None: reads current result and folder dialog]
    # 戻り値: [None: status or error dialog]
    # }
    def export(self) -> None:
        if self.project is None:
            messagebox.showinfo(
                "Pixel Art Creator", "Create or convert an image first.", parent=self
            )
            return
        folder = filedialog.askdirectory()
        if folder:
            try:
                result = self.application.retouch(self.project.grid, ())
                paths = self.application.export(result, Path(folder), "pixel-art")
                self.status.set(f"Exported {paths[0].name} and metadata.")
            except (OSError, ValueError) as error:
                messagebox.showerror("Export error", str(error), parent=self)


# {
# 責務: [_hex_rgba: parse a user RGB brush color]
# 処理: [require six hex digits and return opaque RGBA bytes]
# 引数: [value: entry color string]
# 戻り値: [tuple[int, int, int, int]: brush color]
# }
def _hex_rgba(value: str) -> tuple[int, int, int, int]:
    candidate = value.strip().removeprefix("#")
    if len(candidate) != 6:
        raise ValueError("Brush color must be #RRGGBB.")
    try:
        return (*bytes.fromhex(candidate), 255)
    except ValueError as error:
        raise ValueError("Brush color must be #RRGGBB.") from error


# {
# 責務: [main: launch the standalone Tk root]
# 処理: [start the owning UI event loop]
# 引数: [None: no inputs]
# 戻り値: [None: application exits with window close]
# }
def main() -> None:
    PixelArtWindow().mainloop()
