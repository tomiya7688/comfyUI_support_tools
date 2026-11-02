"""Tk editor for extracting, reviewing, adapting and reusing layouts."""

from __future__ import annotations

import hashlib
import math
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageOps, ImageTk

from comfyui_support_tools.applications.composition_template.ui.commander.application import (
    CompositionTemplateUiCommander,
)
from comfyui_support_tools.shared.contracts.composition_template import (
    AspectPolicy,
    CompositionRegion,
    CompositionTemplate,
    ExtractionLevel,
    ExtractionProvenance,
    HorizonLine,
    RegionRole,
    VanishingPoint,
)


# {
# 責務: [CompositionTemplateWindow: provide an interactive template extraction and reuse interface]
# フィールド: [application, current image/template, preview and region controls]
# 処理: [wire user actions to the Process application and show normalized geometry overlays]
# }
class CompositionTemplateWindow:
    # {
    # 責務: [__init__: assemble the composition template editor]
    # 処理: [create image controls, wireframe canvas, region editor, aspect adaptation and library actions]
    # 引数: [root: Tk root, application: Process application boundary]
    # 戻り値: [None: window initialized]
    # }
    def __init__(self, root: tk.Tk, application: CompositionTemplateUiCommander) -> None:
        self.root = root
        self.application = application
        self.source_path: Path | None = None
        self.source_image: Image.Image | None = None
        self.source_dimensions: tuple[int, int] | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.template: CompositionTemplate | None = None
        self.drag_start: tuple[int, int] | None = None
        self.add_vanishing_point = False
        root.title("Composition Template Extractor")
        root.geometry("1100x760")
        self.status = tk.StringVar(
            value="Open an image to extract its layout. Heuristic results are low-confidence."
        )
        self.selected_region = tk.StringVar()
        self.region_role = tk.StringVar(value=RegionRole.MAIN_SUBJECT.value)
        self.ratio = tk.StringVar(value="1.7778")
        self.policy = tk.StringVar(value=AspectPolicy.FIT.value)
        self.wireframe_only = tk.BooleanVar(value=False)
        self.horizon_y = tk.StringVar(value="0.5")
        self.horizon_angle = tk.StringVar(value="0")
        self._build()

    # {
    # 責務: [_build: construct the editor widgets]
    # 処理: [create action toolbar, preview canvas and normalized region controls]
    # 引数: [self: window]
    # 戻り値: [None: widgets placed]
    # }
    def _build(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill="x")
        for label, callback in (
            ("Open image", self.open_image),
            ("Auto extract", self.extract),
            ("Manual trace", self.manual_trace),
            ("Import JSON", self.import_json),
            ("Export JSON", self.export_json),
            ("Prompt", self.show_prompt),
            ("Guidance", self.export_guidance),
            ("Save template", self.save_template),
            ("Load template", self.load_template),
        ):
            ttk.Button(toolbar, text=label, command=callback).pack(side="left", padx=2)
        body = ttk.Frame(self.root, padding=8)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            body, background="#252525", width=780, height=600, highlightthickness=0
        )
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)
        panel = ttk.Frame(body, width=260, padding=8)
        panel.pack(side="right", fill="y")
        ttk.Checkbutton(
            panel,
            text="Wireframe only",
            variable=self.wireframe_only,
            command=self._render,
        ).pack(anchor="w")
        ttk.Label(panel, text="Composition regions").pack(anchor="w")
        self.region_list = tk.Listbox(panel, height=12, exportselection=False)
        self.region_list.pack(fill="x", pady=4)
        self.region_list.bind("<<ListboxSelect>>", self._select_region)
        ttk.Label(panel, text="Role").pack(anchor="w")
        ttk.Combobox(
            panel,
            textvariable=self.region_role,
            values=[role.value for role in RegionRole],
            state="readonly",
        ).pack(fill="x")
        ttk.Button(panel, text="Apply role", command=self.apply_role).pack(fill="x", pady=(4, 12))
        ttk.Label(panel, text="Target aspect ratio").pack(anchor="w")
        ttk.Entry(panel, textvariable=self.ratio).pack(fill="x")
        ttk.Combobox(
            panel,
            textvariable=self.policy,
            values=[policy.value for policy in AspectPolicy],
            state="readonly",
        ).pack(fill="x", pady=4)
        ttk.Button(panel, text="Adapt", command=self.adapt).pack(fill="x")
        ttk.Label(panel, text="Horizon y / angle").pack(anchor="w", pady=(12, 0))
        horizon_controls = ttk.Frame(panel)
        horizon_controls.pack(fill="x")
        ttk.Entry(horizon_controls, textvariable=self.horizon_y, width=8).pack(
            side="left", fill="x", expand=True
        )
        ttk.Entry(horizon_controls, textvariable=self.horizon_angle, width=8).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(panel, text="Set horizon", command=self.set_horizon).pack(fill="x", pady=4)
        ttk.Button(panel, text="Add vanishing point", command=self.manual_vanishing_point).pack(
            fill="x"
        )
        ttk.Label(self.root, textvariable=self.status, anchor="w", padding=8).pack(fill="x")

    # {
    # 責務: [open_image: choose a source image for layout extraction]
    # 処理: [load an image for preview and retain its path for Process extraction]
    # 引数: [self: window]
    # 戻り値: [None: preview updated]
    # }
    def open_image(self) -> None:
        name = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff")]
        )
        if not name:
            return
        try:
            if Path(name).is_symlink() or Path(name).stat().st_size > 128 * 1024 * 1024:
                raise ValueError("Choose a regular image file below 128 MiB.")
            with Image.open(name) as image:
                if image.width * image.height > 90_000_000:
                    raise ValueError("Image dimensions exceed the 90 megapixel preview limit.")
                preview = ImageOps.exif_transpose(image)
                self.source_dimensions = preview.size
                preview.thumbnail((1560, 1200))
                self.source_image = preview.convert("RGB")
            self.source_path = Path(name)
            self._render()
            self.status.set(
                f"Source: {self.source_path.name}. Appearance is excluded from the saved template."
            )
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            messagebox.showerror("Open image", str(error))

    # {
    # 責務: [extract: create a template from the selected image]
    # 処理: [call the Process application and show confidence/provenance warnings]
    # 引数: [self: window]
    # 戻り値: [None: template and overlay updated]
    # }
    def extract(self) -> None:
        if self.source_path is None:
            messagebox.showinfo("Extract", "Open an image first.")
            return
        try:
            self.template = self.application.extract(self.source_path)
            warnings = "; ".join(self.template.extraction_provenance.warnings)
            self.status.set(
                f"Extracted composition at confidence {self.template.confidence:.2f}. {warnings}"
            )
            self._refresh_regions()
            self._render()
        except (OSError, RuntimeError, ValueError) as error:
            messagebox.showerror("Extract", str(error))

    # {
    # 責務: [manual_trace: add a normalized box by dragging over the preview]
    # 処理: [switch the drag tool on and indicate its assigned composition role]
    # 引数: [self: window]
    # 戻り値: [None: canvas enters manual trace mode]
    # }
    def manual_trace(self) -> None:
        self.region_role.set(RegionRole.MAIN_SUBJECT.value)
        self.status.set("Drag on the image to add a region. Choose a role before tracing.")

    # {
    # 責務: [_drag_start: record the start of a manual region drag]
    # 処理: [clamp the canvas coordinate and store it]
    # 引数: [self: window, event: Tk pointer event]
    # 戻り値: [None: drag origin stored]
    # }
    def _drag_start(self, event: tk.Event) -> None:
        self.drag_start = (event.x, event.y)

    # {
    # 責務: [_drag_end: commit a manually traced region]
    # 処理: [convert canvas geometry to normalized coordinates and append an editable composition role]
    # 引数: [self: window, event: Tk pointer event]
    # 戻り値: [None: new region added]
    # }
    def _drag_end(self, event: tk.Event) -> None:
        if not self.drag_start or not self.source_image:
            return
        x0, y0 = self.drag_start
        self.drag_start = None
        bounds = self.canvas.bbox("image")
        if not bounds:
            return
        left, top, right, bottom = bounds
        x1, y1 = event.x, event.y
        if self.add_vanishing_point:
            self.add_vanishing_point = False
            x = min(1.0, max(0.0, (x1 - left) / (right - left)))
            y = min(1.0, max(0.0, (y1 - top) / (bottom - top)))
            if self.template:
                self.template = replace(
                    self.template,
                    vanishing_points=self.template.vanishing_points + (VanishingPoint(x, y, 1.0),),
                )
                self._render()
                self.status.set(f"Added vanishing point at ({x:.2f}, {y:.2f}).")
            return
        x0, x1 = sorted((max(left, min(right, x0)), max(left, min(right, x1))))
        y0, y1 = sorted((max(top, min(bottom, y0)), max(top, min(bottom, y1))))
        width, height = self.source_image.size
        box = (
            (x0 - left) / (right - left),
            (y0 - top) / (bottom - top),
            (x1 - x0) / (right - left),
            (y1 - y0) / (bottom - top),
        )
        if box[2] <= 0.005 or box[3] <= 0.005:
            return
        role = RegionRole(self.region_role.get())
        if self.template is None:
            source_width, source_height = self.source_dimensions or (width, height)
            self.template = self._empty_template(source_width, source_height)
        category = self._category_for_role(role)
        current = getattr(self.template, category)
        self.template = replace(
            self.template,
            **{
                category: current
                + (
                    CompositionRegion(
                        f"manual-{len(self.template.all_regions) + 1}", role, box, confidence=1.0
                    ),
                )
            },
        )
        self._refresh_regions()
        self._render()

    # {
    # 責務: [_empty_template: create an editable starting layout for manual trace]
    # 処理: [initialize an abstract template with image dimensions and neutral provenance]
    # 引数: [self: window, width: source image width, height: source image height]
    # 戻り値: [CompositionTemplate: empty composition template]
    # }
    def _empty_template(self, width: int, height: int) -> CompositionTemplate:
        image_digest = (
            hashlib.sha256(self.source_path.read_bytes()).hexdigest()
            if self.source_path
            else "0" * 64
        )
        return CompositionTemplate(
            width / height,
            "unknown",
            "unknown",
            (),
            0.0,
            ExtractionProvenance(
                image_digest,
                width,
                height,
                ExtractionLevel.LAYOUT,
                ("manual-trace-v1",),
                ("template created by manual trace",),
            ),
        )

    # {
    # 責務: [_category_for_role: map an edited role to its template region collection]
    # 処理: [preserve foreground, midground, background and other region categories]
    # 引数: [role: composition role]
    # 戻り値: [str: template field name]
    # }
    @staticmethod
    def _category_for_role(role: RegionRole) -> str:
        categories = {
            RegionRole.MAIN_SUBJECT: "subject_regions",
            RegionRole.SUPPORTING_SUBJECT: "subject_regions",
            RegionRole.FOREGROUND: "foreground_regions",
            RegionRole.MIDGROUND: "midground_regions",
            RegionRole.BACKGROUND: "background_regions",
            RegionRole.TEXT_AREA: "text_safe_regions",
            RegionRole.EMPTY_SPACE: "negative_space_regions",
            RegionRole.SALIENT: "salient_regions",
        }
        return categories[role]

    # {
    # 責務: [_refresh_regions: synchronize the region selector with the current template]
    # 処理: [show region IDs and normalized boxes in category order]
    # 引数: [self: window]
    # 戻り値: [None: listbox refreshed]
    # }
    def _refresh_regions(self) -> None:
        self.region_list.delete(0, tk.END)
        if self.template:
            for region in self.template.all_regions:
                self.region_list.insert(
                    tk.END,
                    f"{region.id} · {region.role.value} · {tuple(round(value, 2) for value in region.bbox)}",
                )

    # {
    # 責務: [_select_region: load the selected role into the editor]
    # 処理: [resolve the selected list row against the immutable template]
    # 引数: [self: window, event: Tk listbox event]
    # 戻り値: [None: role editor synchronized]
    # }
    def _select_region(self, _event: tk.Event) -> None:
        if not self.template or not self.region_list.curselection():
            return
        region = self.template.all_regions[self.region_list.curselection()[0]]
        self.region_role.set(region.role.value)

    # {
    # 責務: [apply_role: change the selected region's composition role]
    # 処理: [replace immutable region data and move it to the matching template category]
    # 引数: [self: window]
    # 戻り値: [None: region category updated]
    # }
    def apply_role(self) -> None:
        if not self.template or not self.region_list.curselection():
            return
        selected = self.template.all_regions[self.region_list.curselection()[0]]
        updated = replace(selected, role=RegionRole(self.region_role.get()))
        categories = (
            "subject_regions",
            "foreground_regions",
            "midground_regions",
            "background_regions",
            "negative_space_regions",
            "salient_regions",
            "text_safe_regions",
            "optional_panel_layout",
        )
        values = {
            name: tuple(
                region for region in getattr(self.template, name) if region.id != selected.id
            )
            for name in categories
        }
        role = updated.role
        target = self._category_for_role(role)
        values[target] += (updated,)
        self.template = replace(self.template, **values)
        self._refresh_regions()
        self._render()

    # {
    # 責務: [set_horizon: set or edit the normalized horizon cue]
    # 処理: [validate the user-entered height and angle and update template evidence]
    # 引数: [self: window]
    # 戻り値: [None: horizon overlay updated]
    # }
    def set_horizon(self) -> None:
        if not self.template:
            messagebox.showinfo("Set horizon", "Extract a template or add a manual region first.")
            return
        try:
            self.template = replace(
                self.template,
                horizon=HorizonLine(
                    float(self.horizon_y.get()), float(self.horizon_angle.get()), 1.0
                ),
            )
            self._render()
            self.status.set("Horizon updated.")
        except ValueError as error:
            messagebox.showerror("Set horizon", str(error))

    # {
    # 責務: [manual_vanishing_point: arm one canvas click to add a perspective point]
    # 処理: [set a one-shot canvas interaction mode]
    # 引数: [self: window]
    # 戻り値: [None: next canvas click adds a point]
    # }
    def manual_vanishing_point(self) -> None:
        if not self.template:
            messagebox.showinfo(
                "Vanishing point", "Extract a template or add a manual region first."
            )
            return
        self.add_vanishing_point = True
        self.status.set("Click the canvas to place a vanishing point.")

    # {
    # 責務: [adapt: apply selected aspect ratio and geometry policy]
    # 処理: [validate controls and request an immutable transformed template]
    # 引数: [self: window]
    # 戻り値: [None: adapted preview displayed]
    # }
    def adapt(self) -> None:
        if not self.template:
            return
        try:
            self.template = self.application.adapt(
                self.template, float(self.ratio.get()), AspectPolicy(self.policy.get())
            )
            self._refresh_regions()
            self._render()
            self.status.set(
                f"Adapted to {self.template.aspect_ratio:.3f} using {self.policy.get()} (no stretching)."
            )
        except (ValueError, OverflowError) as error:
            messagebox.showerror("Adapt", str(error))

    # {
    # 責務: [_render: draw source pixels and layout overlay]
    # 処理: [fit a preview thumbnail to canvas and paint normalized role boxes]
    # 引数: [self: window]
    # 戻り値: [None: canvas redrawn]
    # }
    def _render(self) -> None:
        self.canvas.delete("all")
        if not self.source_image and not self.template:
            return
        ratio = (
            self.template.aspect_ratio
            if self.template
            else self.source_image.width / self.source_image.height
        )
        width, height = (
            (780, max(1, round(780 / ratio))) if ratio >= 1 else (max(1, round(600 * ratio)), 600)
        )
        if not self.source_image or self.wireframe_only.get():
            preview = Image.new("RGB", (width, height), "#f2f2f2")
        elif self.policy.get() == AspectPolicy.CROP.value:
            preview = ImageOps.fit(self.source_image, (width, height))
        else:
            fitted = ImageOps.contain(self.source_image, (width, height))
            preview = Image.new("RGB", (width, height), "#f2f2f2")
            preview.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
        left, top = (780 - preview.width) // 2, (600 - preview.height) // 2
        if not self.template:
            self.preview_photo = ImageTk.PhotoImage(preview)
            self.canvas.create_image(left, top, anchor="nw", image=self.preview_photo, tags="image")
            return
        draw = ImageDraw.Draw(preview, "RGBA")
        if self.template.visual_weight_map:
            rows = self.template.visual_weight_map.rows
            cell_width, cell_height = preview.width / len(rows[0]), preview.height / len(rows)
            for row_index, row in enumerate(rows):
                for column_index, weight in enumerate(row):
                    if weight >= 0.35:
                        draw.rectangle(
                            (
                                column_index * cell_width,
                                row_index * cell_height,
                                (column_index + 1) * cell_width,
                                (row_index + 1) * cell_height,
                            ),
                            fill=(240, 70, 30, int(25 + weight * 70)),
                        )
        colors = {
            RegionRole.MAIN_SUBJECT: (255, 80, 80, 230),
            RegionRole.SUPPORTING_SUBJECT: (255, 150, 60, 230),
            RegionRole.EMPTY_SPACE: (80, 180, 255, 180),
            RegionRole.TEXT_AREA: (100, 240, 130, 200),
        }
        for region in self.template.all_regions:
            x, y, width, height = region.bbox
            color = colors.get(region.role, (230, 220, 80, 210))
            draw.rectangle(
                (
                    x * preview.width,
                    y * preview.height,
                    (x + width) * preview.width,
                    (y + height) * preview.height,
                ),
                outline=color,
                width=2,
            )
        if self.template.horizon:
            horizon_y = self.template.horizon.y * preview.height
            slope = -math.tan(math.radians(self.template.horizon.angle))
            draw.line(
                (
                    0,
                    horizon_y + slope * preview.width / 2,
                    preview.width,
                    horizon_y - slope * preview.width / 2,
                ),
                fill=(70, 210, 255, 240),
                width=2,
            )
        for point in self.template.vanishing_points:
            x, y = point.x * preview.width, point.y * preview.height
            draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 40, 220, 240))
        for skeleton in self.template.pose_skeletons:
            points = [
                (keypoint.point[0] * preview.width, keypoint.point[1] * preview.height)
                for keypoint in skeleton.keypoints
                if keypoint.visibility > 0.1
            ]
            for start, end in zip(points, points[1:], strict=False):
                draw.line((*start, *end), fill=(40, 255, 150, 230), width=2)
            for x, y in points:
                draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(40, 255, 150, 240))
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.canvas.create_image(left, top, anchor="nw", image=self.preview_photo, tags="image")

    # {
    # 責務: [import_json: import an externally edited abstract template]
    # 処理: [read a selected JSON document and validate it through the Data messenger]
    # 引数: [self: window]
    # 戻り値: [None: imported template displayed]
    # }
    def import_json(self) -> None:
        name = filedialog.askopenfilename(filetypes=[("Composition template JSON", "*.json")])
        if not name:
            return
        try:
            self.template = self.application.import_file(name)
            self._refresh_regions()
            self._render()
            self.status.set(f"Imported {Path(name).name}")
        except (OSError, ValueError) as error:
            messagebox.showerror("Import template", str(error))

    # {
    # 責務: [export_json: export the current abstract template]
    # 処理: [serialize through Data messenger and write the chosen JSON file]
    # 引数: [self: window]
    # 戻り値: [None: template JSON saved]
    # }
    def export_json(self) -> None:
        if not self.template:
            return
        name = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("Composition template JSON", "*.json")]
        )
        if name:
            try:
                self.application.export_file(name, self.template)
                self.status.set(f"Exported {Path(name).name}")
            except (OSError, ValueError) as error:
                messagebox.showerror("Export template", str(error))

    # {
    # 責務: [save_template: save a reusable named library template]
    # 処理: [ask for a safe name and route to the template library]
    # 引数: [self: window]
    # 戻り値: [None: library template saved]
    # }
    def save_template(self) -> None:
        if not self.template:
            return
        name = simpledialog.askstring(
            "Save template", "Template name (letters, digits, _ and -):", parent=self.root
        )
        if name:
            try:
                path = self.application.save(name, self.template)
                self.status.set(f"Saved {path.name}")
            except (OSError, ValueError, FileExistsError) as error:
                messagebox.showerror("Save template", str(error))

    # {
    # 責務: [load_template: load a saved reusable layout]
    # 処理: [choose from the Data library and display the stored template]
    # 引数: [self: window]
    # 戻り値: [None: library template displayed]
    # }
    def load_template(self) -> None:
        names = self.application.list_templates()
        if not names:
            messagebox.showinfo("Load template", "The template library is empty.")
            return
        name = simpledialog.askstring(
            "Load template", "Available: " + ", ".join(names), parent=self.root
        )
        if name:
            try:
                self.template = self.application.load(name)
                self._refresh_regions()
                self._render()
                self.status.set(f"Loaded {name}")
            except (OSError, ValueError) as error:
                messagebox.showerror("Load template", str(error))

    # {
    # 責務: [show_prompt: preview the appearance-free generation prompt]
    # 処理: [display the Process prompt export in a read-only dialog]
    # 引数: [self: window]
    # 戻り値: [None: prompt shown]
    # }
    def show_prompt(self) -> None:
        if self.template:
            messagebox.showinfo("Composition prompt", self.application.prompt(self.template))

    # {
    # 責務: [export_guidance: save generic downstream generation guidance]
    # 処理: [write versioned guidance JSON to a user-selected destination]
    # 引数: [self: window]
    # 戻り値: [None: guidance exported]
    # }
    def export_guidance(self) -> None:
        if not self.template:
            return
        name = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("Generation guidance", "*.json")]
        )
        if name:
            try:
                self.application.export_guidance_file(name, self.template)
                self.status.set(f"Guidance exported to {Path(name).name}")
            except (OSError, ValueError) as error:
                messagebox.showerror("Export guidance", str(error))


# {
# 責務: [launch: start the composition template editor]
# 処理: [configure the standard user library and launch Tk main loop]
# 引数: [none]
# 戻り値: [None: GUI exits when its window closes]
# }
def launch(application: CompositionTemplateUiCommander) -> None:
    root = tk.Tk()
    CompositionTemplateWindow(root, application)
    root.mainloop()
