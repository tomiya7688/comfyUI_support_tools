"""Tk editor for sparse point and scribble guidance hints."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageFilter, ImageTk

from scripts.backend.guidance_document import (
    GuidanceHints,
    GuidancePoint,
    GuidanceScribble,
    save_guidance,
)


# {
#   責務: [GuidanceEditor: image上のsparse point/scribble hintsを作成・保存する]
#   フィールド: [source image, normalized annotations, brush mode, semantic category/material]
#   処理: [draw/undo/clear annotations and save local guidance-hints.v1 JSON]
# }
class GuidanceEditor(tk.Toplevel):
    # {
    #   責務: [__init__: image preview, toolbar and annotation stateを初期化する]
    #   処理: [bind mouse events and retain a resize-aware source image preview]
    #   引数: [master: parent window, image: source RGB image, save_path: local JSON path, on_saved: optional callback, initial_hints: optional saved hints]
    #   戻り値: []
    # }
    def __init__(
        self,
        master,
        image: Image.Image,
        save_path: Path,
        on_saved=None,
        initial_hints: GuidanceHints | None = None,
        source_sha256: str = "",
    ) -> None:
        super().__init__(master)
        self.title("Touka Interactive Guidance")
        self.geometry("1000x720")
        self._source = image.convert("RGB")
        self._save_path = Path(save_path)
        self._on_saved = on_saved
        self._source_sha256 = source_sha256
        self._points = list(initial_hints.points if initial_hints else ())
        self._scribbles = list(initial_hints.scribbles if initial_hints else ())
        self._history = [("point", index) for index in range(len(self._points))]
        self._history.extend(("scribble", index) for index in range(len(self._scribbles)))
        self._preview = None
        self._display_box = (0, 0, 1, 1)
        self._active_stroke = None
        self._mode = tk.StringVar(value="point:hidden_object")
        self._confidence = tk.DoubleVar(value=initial_hints.confidence if initial_hints else 0.7)
        self._category = tk.StringVar(value=initial_hints.category if initial_hints else "")
        self._material = tk.StringVar(value=initial_hints.material if initial_hints else "")
        self._build()
        self.bind("<Configure>", self._schedule_draw)
        self.after_idle(self._draw)

    # {
    #   責務: [_build: annotation controlsとpreview canvasを構成する]
    #   処理: [offer point labels, brush scribble classes, confidence, semantic category/material and edit actions]
    #   引数: [self: GuidanceEditor]
    #   戻り値: []
    # }
    def _build(self) -> None:
        controls = ttk.Frame(self, padding=8)
        controls.pack(fill="x")
        ttk.Label(controls, text="Hint").pack(side="left")
        choices = (
            "point:surface",
            "point:hidden_object",
            "point:background",
            "point:edge",
            "point:color_sample",
            "scribble:surface",
            "scribble:hidden_object",
            "scribble:exclude",
            "scribble:contour",
        )
        ttk.Combobox(
            controls, textvariable=self._mode, values=choices, state="readonly", width=24
        ).pack(side="left", padx=4)
        ttk.Label(controls, text="Confidence").pack(side="left", padx=(12, 2))
        ttk.Scale(controls, from_=0.1, to=1.0, variable=self._confidence, length=140).pack(
            side="left"
        )
        ttk.Label(controls, text="Category").pack(side="left", padx=(12, 2))
        ttk.Combobox(
            controls,
            textvariable=self._category,
            values=("", "generic", "clothing", "cloth", "shirt", "skin", "paper", "film", "other"),
            state="readonly",
            width=12,
        ).pack(side="left")
        ttk.Label(controls, text="Material").pack(side="left", padx=(8, 2))
        ttk.Combobox(
            controls,
            textvariable=self._material,
            values=("", "cloth", "thin_cloth", "thick_cloth", "paper", "plastic", "glass", "other"),
            state="readonly",
            width=12,
        ).pack(side="left")
        ttk.Button(controls, text="Auto suggestion", command=self.suggest_edge).pack(
            side="left", padx=(12, 3)
        )
        ttk.Button(controls, text="Undo", command=self.undo).pack(side="left", padx=3)
        ttk.Button(controls, text="Clear", command=self.clear).pack(side="left", padx=3)
        ttk.Button(controls, text="Save hints", command=self.save).pack(side="right")
        ttk.Label(
            self,
            text="Hints are soft priors. Review warnings when color samples or region labels disagree with the image.",
        ).pack(anchor="w", padx=8, pady=(0, 5))
        self._canvas = tk.Canvas(self, background="#20242b", highlightthickness=0)
        self._canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._canvas.bind("<ButtonPress-1>", self._press)
        self._canvas.bind("<B1-Motion>", self._drag)
        self._canvas.bind("<ButtonRelease-1>", self._release)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # {
    #   責務: [_schedule_draw: resizeの連続eventを描画1回へまとめる]
    #   処理: [schedule an idle redraw for the scaled source preview]
    #   引数: [self: GuidanceEditor, event: configure event]
    #   戻り値: []
    # }
    def _schedule_draw(self, _event=None) -> None:
        if self.winfo_exists():
            self.after_idle(self._draw)

    # {
    #   責務: [_draw: fit imageをcanvasへ描きannotation overlayを更新する]
    #   処理: [draw source image, points and scribbles at normalized positions]
    #   引数: [self: GuidanceEditor]
    #   戻り値: []
    # }
    def _draw(self) -> None:
        width, height = max(1, self._canvas.winfo_width()), max(1, self._canvas.winfo_height())
        scale = min(width / self._source.width, height / self._source.height)
        display_size = (
            max(1, round(self._source.width * scale)),
            max(1, round(self._source.height * scale)),
        )
        preview = self._source.resize(display_size, Image.Resampling.LANCZOS)
        self._preview = ImageTk.PhotoImage(preview)
        left, top = (width - display_size[0]) // 2, (height - display_size[1]) // 2
        self._display_box = (left, top, display_size[0], display_size[1])
        self._canvas.delete("all")
        self._canvas.create_image(left, top, anchor="nw", image=self._preview)
        for point in self._points:
            x, y = self._canvas_position(point.x, point.y)
            color = _LABEL_COLORS.get(point.label, "#ffff00")
            self._canvas.create_oval(x - 5, y - 5, x + 5, y + 5, outline=color, width=2)
            self._canvas.create_text(x + 8, y - 8, anchor="nw", text=point.label, fill=color)
        for stroke in self._scribbles:
            color = _LABEL_COLORS.get(stroke.label, "#ffff00")
            coordinates = [
                coordinate for x, y in stroke.points for coordinate in self._canvas_position(x, y)
            ]
            width_px = max(2, round(min(display_size) * stroke.width))
            if len(coordinates) == 2:
                x, y = coordinates
                self._canvas.create_oval(
                    x - width_px,
                    y - width_px,
                    x + width_px,
                    y + width_px,
                    fill=color,
                    outline=color,
                )
            else:
                self._canvas.create_line(
                    *coordinates, fill=color, width=width_px, capstyle="round", joinstyle="round"
                )

    # {
    #   責務: [_press: click locationでpointを追加するかscribbleを開始する]
    #   処理: [ignore clicks outside fitted image region]
    #   引数: [self: GuidanceEditor, event: mouse press]
    #   戻り値: []
    # }
    def _press(self, event) -> None:
        point = self._normalized_position(event.x, event.y)
        if point is None:
            return
        kind, label = self._mode.get().split(":", 1)
        if kind == "point":
            expected = (
                self._source.getpixel(
                    (
                        round(point[0] * (self._source.width - 1)),
                        round(point[1] * (self._source.height - 1)),
                    )
                )
                if label == "color_sample"
                else None
            )
            self._points.append(GuidancePoint(*point, label, self._confidence.get(), expected))
            self._history.append(("point", len(self._points) - 1))
            self._draw()
        else:
            self._active_stroke = [point]

    # {
    #   責務: [_drag: active scribbleにnormalized pointer locationを加える]
    #   処理: [avoid repeated adjacent identical coordinates]
    #   引数: [self: GuidanceEditor, event: mouse motion]
    #   戻り値: []
    # }
    def _drag(self, event) -> None:
        point = self._normalized_position(event.x, event.y)
        if point is None or self._active_stroke is None:
            return
        if not self._active_stroke or point != self._active_stroke[-1]:
            self._active_stroke.append(point)
        self._draw()

    # {
    #   責務: [_release: completed scribbleをvalidated contractへ追加する]
    #   処理: [save normalized points, label and soft confidence]
    #   引数: [self: GuidanceEditor, event: mouse release]
    #   戻り値: []
    # }
    def _release(self, _event) -> None:
        if self._active_stroke is None:
            return
        kind, label = self._mode.get().split(":", 1)
        if kind == "scribble":
            points = tuple(self._active_stroke)
            self._scribbles.append(GuidanceScribble(points, label, 0.035, self._confidence.get()))
            self._history.append(("scribble", len(self._scribbles) - 1))
        self._active_stroke = None
        self._draw()

    # {
    #   責務: [_normalized_position: displayed canvas coordinateをimage-relative locationへ変換する]
    #   処理: [exclude letterboxed areas and clamp to image bounds]
    #   引数: [self: GuidanceEditor, x/y: canvas pixel coordinates]
    #   戻り値: [tuple[float, float] | None: normalized point]
    # }
    def _normalized_position(self, x: int, y: int) -> tuple[float, float] | None:
        left, top, width, height = self._display_box
        if not left <= x <= left + width or not top <= y <= top + height:
            return None
        return min(1.0, max(0.0, (x - left) / max(1, width - 1))), min(
            1.0, max(0.0, (y - top) / max(1, height - 1))
        )

    # {
    #   責務: [_canvas_position: normalized image locationをCanvas coordinateへ変換する]
    #   処理: [apply preview offset and display size]
    #   引数: [self: GuidanceEditor, x/y: normalized values]
    #   戻り値: [tuple[float, float]: canvas coordinates]
    # }
    def _canvas_position(self, x: float, y: float) -> tuple[float, float]:
        left, top, width, height = self._display_box
        return left + x * width, top + y * height

    # {
    #   責務: [suggest_edge: low-confidence image heuristicからedge point案を追加する]
    #   処理: [search a bounded thumbnail edge map and add one explicitly low-confidence hint]
    #   引数: [self: GuidanceEditor]
    #   戻り値: []
    # }
    def suggest_edge(self) -> None:
        thumbnail = self._source.convert("L").resize((256, 256), Image.Resampling.BILINEAR)
        edge_map = thumbnail.filter(ImageFilter.FIND_EDGES)
        values = list(edge_map.getdata())
        if not values or max(values) < 12:
            messagebox.showinfo(
                "Auto suggestion", "Strong edge evidence was not found.", parent=self
            )
            return
        index = values.index(max(values))
        x, y = index % 256, index // 256
        point = GuidancePoint(x / 255, y / 255, "edge", 0.35)
        self._points.append(point)
        self._history.append(("point", len(self._points) - 1))
        self._draw()

    # {
    #   責務: [undo: 最後のannotationを取り消す]
    #   処理: [remove most recently added point or scribble]
    #   引数: [self: GuidanceEditor]
    #   戻り値: []
    # }
    def undo(self) -> None:
        if self._history:
            kind, index = self._history.pop()
            items = self._points if kind == "point" else self._scribbles
            if index < len(items):
                items.pop(index)
            self._history = [
                (entry_kind, entry_index - (entry_kind == kind and entry_index > index))
                for entry_kind, entry_index in self._history
            ]
        self._draw()

    # {
    #   責務: [clear: 保存前の全hintを解除する]
    #   処理: [clear all points and strokes and redraw the unannotated source]
    #   引数: [self: GuidanceEditor]
    #   戻り値: []
    # }
    def clear(self) -> None:
        self._points.clear()
        self._scribbles.clear()
        self._history.clear()
        self._draw()

    # {
    #   責務: [save: validated guidance contractをlocal fileへ保存する]
    #   処理: [save category/material and hint points, then invoke optional callback]
    #   引数: [self: GuidanceEditor]
    #   戻り値: []
    # }
    def save(self) -> None:
        try:
            hints = GuidanceHints(
                points=tuple(self._points),
                scribbles=tuple(self._scribbles),
                category=self._category.get(),
                material=self._material.get(),
                confidence=self._confidence.get(),
                source_sha256=self._source_sha256,
            )
            path = save_guidance(self._save_path, hints)
        except (OSError, ValueError) as error:
            messagebox.showerror("Guidance save failed", str(error), parent=self)
            return
        if self._on_saved:
            self._on_saved(path, hints)
        self.destroy()


_LABEL_COLORS = {
    "surface": "#55d6be",
    "hidden_object": "#ff6b6b",
    "background": "#9b8cff",
    "edge": "#ffd166",
    "color_sample": "#f8f9fa",
    "exclude": "#868e96",
    "contour": "#ff922b",
}
