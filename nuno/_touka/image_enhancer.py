"""General-purpose image enhancement utility.

Run ``python image_enhancer.py`` for the desktop UI, or use ``--smoke-test``
to exercise the processing pipeline without opening a window.
"""
from __future__ import annotations

import argparse
import os
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Sequence

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageTk


def _curve_lut(points: Sequence[tuple[float, float]]) -> np.ndarray:
    """Return a 256-entry monotonic-ish LUT from normalized control points."""
    pts = sorted((float(x), float(y)) for x, y in points)
    x, y = zip(*pts)
    values = np.interp(np.arange(256) / 255.0, x, y) * 255.0
    return np.clip(values, 0, 255).astype(np.uint8)


@dataclass
class EnhanceSettings:
    master_curve: list[tuple[float, float]] = field(default_factory=lambda: [(0, 0), (1, 1)])
    red_curve: list[tuple[float, float]] = field(default_factory=lambda: [(0, 0), (1, 1)])
    green_curve: list[tuple[float, float]] = field(default_factory=lambda: [(0, 0), (1, 1)])
    blue_curve: list[tuple[float, float]] = field(default_factory=lambda: [(0, 0), (1, 1)])
    contrast: float = 0.0       # -100..100
    highlights: float = 0.0     # -100..100
    shadows: float = 0.0       # -100..100
    detail: float = 0.0         # 0..100
    blend_mode: str = "Normal"
    opacity: float = 50.0       # 0..100
    passes: int = 1


def _apply_curves(rgb: np.ndarray, settings: EnhanceSettings) -> np.ndarray:
    out = rgb
    master = _curve_lut(settings.master_curve)
    out = master[np.clip(out, 0, 255).astype(np.uint8)]
    for idx, points in enumerate((settings.red_curve, settings.green_curve, settings.blue_curve)):
        lut = _curve_lut(points)
        out[..., idx] = lut[np.clip(out[..., idx], 0, 255).astype(np.uint8)]
    return out


def enhance_copy(image: Image.Image, settings: EnhanceSettings) -> Image.Image:
    """Make one processed copy, keeping the source image unchanged."""
    source = image.convert("RGBA")
    alpha = np.asarray(source)[..., 3].copy()
    rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
    rgb = _apply_curves(rgb, settings).astype(np.float32)
    # Contrast is centered around middle gray.  Values are intentionally gentle.
    factor = max(0.0, 1.0 + settings.contrast / 100.0)
    rgb = (rgb - 127.5) * factor + 127.5
    # Highlights affect the brighter half; shadows affect the darker half.
    lum = rgb.mean(axis=2) / 255.0
    rgb += settings.highlights * 1.15 * np.clip((lum - 0.45) / 0.55, 0, 1)[..., None]
    rgb += settings.shadows * 1.15 * np.clip((0.55 - lum) / 0.55, 0, 1)[..., None]
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    result = Image.fromarray(np.dstack((rgb, alpha)), "RGBA")
    if settings.detail > 0:
        # UnsharpMask provides a predictable, local detail boost without changing size.
        radius = 0.6 + settings.detail / 100.0 * 1.8
        percent = int(40 + settings.detail * 2.2)
        sharpened = result.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=2))
        result = Image.blend(result, sharpened, settings.detail / 100.0)
    return result


def _blend_rgb(base: np.ndarray, layer: np.ndarray, mode: str) -> np.ndarray:
    a, b = base / 255.0, layer / 255.0
    mode = mode.lower()
    if mode == "darken": out = np.minimum(a, b)
    elif mode == "lighten": out = np.maximum(a, b)
    elif mode == "multiply": out = a * b
    elif mode == "screen": out = 1 - (1 - a) * (1 - b)
    elif mode == "overlay": out = np.where(a <= 0.5, 2 * a * b, 1 - 2 * (1 - a) * (1 - b))
    else: out = b
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


def process_image(image: Image.Image, settings: EnhanceSettings) -> Image.Image:
    """Process and blend one or more copies back over the original."""
    base = image.convert("RGBA")
    result = base.copy()
    for _ in range(max(1, int(settings.passes))):
        layer = enhance_copy(result, settings)
        base_rgb = np.asarray(result.convert("RGB"))
        layer_rgb = np.asarray(layer.convert("RGB"))
        blended = _blend_rgb(base_rgb, layer_rgb, settings.blend_mode)
        amount = np.clip(settings.opacity / 100.0, 0, 1)
        mixed = (base_rgb.astype(np.float32) * (1 - amount) + blended * amount).astype(np.uint8)
        result = Image.fromarray(np.dstack((mixed, np.asarray(result)[..., 3])), "RGBA")
    return result


class CurveEditor(tk.Canvas):
    def __init__(self, master, channel: str, changed: Callable[[], None], **kwargs):
        super().__init__(master, width=190, height=150, bg="#20242b", highlightthickness=0, **kwargs)
        self.channel, self.changed = channel, changed
        self.points = [(0.0, 0.0), (1.0, 1.0)]
        self.drag_index: int | None = None
        self.bind("<Button-1>", self._click)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda _e: setattr(self, "drag_index", None))
        self._draw()

    def reset(self):
        self.points = [(0.0, 0.0), (1.0, 1.0)]
        self._draw(); self.changed()

    def get_points(self): return list(self.points)

    def _xy(self, p): return (8 + p[0] * 174, 142 - p[1] * 134)
    def _point_at(self, event):
        return min(range(len(self.points)), key=lambda i: (self._xy(self.points[i])[0]-event.x)**2 + (self._xy(self.points[i])[1]-event.y)**2)

    def _click(self, event):
        i = self._point_at(event)
        x, y = self._xy(self.points[i])
        if (x-event.x)**2 + (y-event.y)**2 < 180:
            self.drag_index = i
        elif 8 <= event.x <= 182 and 8 <= event.y <= 142 and len(self.points) < 8:
            inserted = ((event.x-8)/174, (142-event.y)/134)
            self.points.append(inserted); self.points.sort(); self.drag_index = self.points.index(inserted)
            self._draw(); self.changed()

    def _drag(self, event):
        if self.drag_index is None: return
        i = self.drag_index
        x, y = np.clip((event.x-8)/174, 0, 1), np.clip((142-event.y)/134, 0, 1)
        if i == 0: x = 0
        if i == len(self.points)-1: x = 1
        if 0 < i < len(self.points)-1: x = np.clip(x, self.points[i-1][0]+.005, self.points[i+1][0]-.005)
        self.points[i] = (float(x), float(y)); self._draw(); self.changed()

    def _draw(self):
        self.delete("all")
        for n in range(0, 6):
            x = 8 + n * 34.8; y = 142 - n * 26.8
            self.create_line(x, 8, x, 142, fill="#353b45"); self.create_line(8, y, 182, y, fill="#353b45")
        if len(self.points) > 1:
            coords = [v for p in self.points for v in self._xy(p)]
            self.create_line(*coords, fill="#76b9ff", width=2)
        for p in self.points:
            x, y = self._xy(p); self.create_oval(x-4, y-4, x+4, y+4, fill="#fff", outline="#76b9ff")
        self.create_text(95, 148, text=self.channel, fill="#cfd6e0")


class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title("Image Enhancer"); self.geometry("1240x720"); self.minsize(1020, 600)
        self.source: Image.Image | None = None; self.preview: ImageTk.PhotoImage | None = None; self.after_id = None; self.roi = None; self.roi_start = None; self.display_size = (1,1); self.object_mask = None
        self._build(); self._set_status("Open an image to begin.")

    def _build(self):
        toolbar = ttk.Frame(self, padding=8); toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Open…", command=self.open_image).pack(side="left")
        ttk.Button(toolbar, text="Save export…", command=self.save_image).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Reset all", command=self.reset_all).pack(side="left")
        ttk.Button(toolbar, text="Auto object", command=self.auto_object).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Clear selection", command=self.clear_selection).pack(side="left")
        self.show_original = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="Show original", variable=self.show_original, command=self.update_preview).pack(side="left", padx=12)
        self.status = ttk.Label(toolbar); self.status.pack(side="right")
        body = ttk.Frame(self, padding=(8, 0)); body.pack(fill="both", expand=True)
        self.preview_label = tk.Canvas(body, background="#20242b", highlightthickness=0); self.preview_label.pack(side="left", fill="both", expand=True)
        self.preview_label.bind("<ButtonPress-1>", self._roi_press); self.preview_label.bind("<B1-Motion>", self._roi_drag); self.preview_label.bind("<ButtonRelease-1>", self._roi_release); self.preview_label.bind("<Button-3>", self._click_object)
        panel = ttk.Frame(body, width=420); panel.pack(side="right", fill="y", padx=(12, 0)); panel.pack_propagate(False)
        curves = ttk.LabelFrame(panel, text="RGB tone curves", padding=5); curves.pack(fill="x")
        self.curves = {}
        for index, name in enumerate(("Master RGB", "Red", "Green", "Blue")):
            editor = CurveEditor(curves, name, self.schedule_preview)
            editor.grid(row=index // 2, column=index % 2, padx=2, pady=2)
            self.curves[name] = editor
        self.vars = {}
        for label, key, lo, hi, default in (("Contrast", "contrast", -100, 100, 0), ("Highlights", "highlights", -100, 100, 0), ("Shadows", "shadows", -100, 100, 0), ("Detail / sharpen", "detail", 0, 100, 0), ("Opacity", "opacity", 0, 100, 50)):
            row = ttk.Frame(panel); row.pack(fill="x", pady=3); ttk.Label(row, text=label, width=17).pack(side="left")
            var = tk.DoubleVar(value=default); self.vars[key] = var
            scale = ttk.Scale(row, from_=lo, to=hi, variable=var, command=lambda _v: self.schedule_preview()); scale.pack(side="left", fill="x", expand=True)
            ttk.Label(row, textvariable=var, width=5).pack(side="right")
        row = ttk.Frame(panel); row.pack(fill="x", pady=3); ttk.Label(row, text="Repeated passes (1–5)", width=17).pack(side="left")
        self.vars["passes"] = tk.IntVar(value=1)
        spin = tk.Spinbox(row, from_=1, to=5, width=5, textvariable=self.vars["passes"], command=self.schedule_preview)
        spin.pack(side="left"); spin.bind("<KeyRelease>", lambda _e: self.schedule_preview())
        row = ttk.Frame(panel); row.pack(fill="x", pady=3); ttk.Label(row, text="Blend mode", width=17).pack(side="left")
        self.mode = tk.StringVar(value="Normal"); ttk.Combobox(row, textvariable=self.mode, values=("Normal", "Darken", "Lighten", "Multiply", "Screen", "Overlay"), state="readonly", width=12).pack(side="left"); self.mode.trace_add("write", lambda *_: self.schedule_preview())
        ttk.Label(panel, text="General-purpose tool for non-person imagery. It can enhance visible differences, but cannot recover information absent from the source.", wraplength=400).pack(anchor="w", pady=8)
        ttk.Label(panel, text="Click to add curve points; drag points to shape the response.", wraplength=400).pack(anchor="w", pady=3)

    def _settings(self):
        try:
            passes = int(self.vars["passes"].get())
        except (tk.TclError, ValueError):
            passes = 1
        passes = max(1, min(5, passes))
        return EnhanceSettings(master_curve=self.curves["Master RGB"].get_points(), red_curve=self.curves["Red"].get_points(), green_curve=self.curves["Green"].get_points(), blue_curve=self.curves["Blue"].get_points(), contrast=self.vars["contrast"].get(), highlights=self.vars["highlights"].get(), shadows=self.vars["shadows"].get(), detail=self.vars["detail"].get(), blend_mode=self.mode.get(), opacity=self.vars["opacity"].get(), passes=passes)

    def _set_status(self, text): self.status.configure(text=text)
    def reset_all(self):
        for editor in self.curves.values(): editor.reset()
        for key, value in (("contrast", 0), ("highlights", 0), ("shadows", 0), ("detail", 0), ("opacity", 50), ("passes", 1)):
            self.vars[key].set(value)
        self.mode.set("Normal"); self.show_original.set(False); self.schedule_preview()
    def schedule_preview(self):
        if self.after_id: self.after_cancel(self.after_id)
        self.after_id = self.after(120, self.update_preview)
    def open_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.tif *.tiff *.bmp"), ("All files", "*.*")])
        if not path: return
        try: self.source = ImageOps.exif_transpose(Image.open(path)).convert("RGBA"); self._set_status(os.path.basename(path)); self.update_preview()
        except Exception as exc: messagebox.showerror("Open failed", str(exc))
    def _roi_press(self, event): self.roi_start=(event.x,event.y)
    def _roi_drag(self, event):
        if self.roi_start: self.preview_label.delete("roi"); self.preview_label.create_rectangle(*self.roi_start,event.x,event.y,outline="#55d6ff",width=2,tags="roi")
    def _roi_release(self, event):
        if not self.roi_start: return
        x0,y0=self.roi_start; self.roi_start=None; w,h=self.display_size
        self.roi=tuple(max(0,min(1,v)) for v in (min(x0,event.x)/w,min(y0,event.y)/h,max(x0,event.x)/w,max(y0,event.y)/h)); self.update_preview()
    def _click_object(self, event): self._grabcut((event.x/event.widget.winfo_width(), event.y/event.widget.winfo_height()))
    def auto_object(self): self._grabcut(None)
    def _grabcut(self, point):
        if self.source is None: return
        arr=np.array(self.source.convert("RGB")); h,w=arr.shape[:2]; mask=np.zeros((h,w),np.uint8)
        if point: x,y=int(point[0]*w),int(point[1]*h); rect=(max(0,x-w//5),max(0,y-h//5),min(w,w*2//5),min(h,h*2//5))
        else: rect=(w//10,h//10,w*8//10,h*8//10)
        bgd=np.zeros((1,65),np.float64); fgd=np.zeros((1,65),np.float64); cv2.grabCut(arr,mask,rect,bgd,fgd,3,cv2.GC_INIT_WITH_RECT); self.object_mask=Image.fromarray(np.where((mask==1)|(mask==3),255,0).astype("uint8")); self.update_preview()
    def clear_selection(self): self.roi=None; self.object_mask=None; self.update_preview()
    def update_preview(self):
        self.after_id = None
        if self.source is None: return
        im = self.source.copy(); im.thumbnail((780, 650), Image.Resampling.LANCZOS)
        out = im if self.show_original.get() else process_image(im, self._settings())
        if not self.show_original.get() and self.object_mask is not None:
            out = Image.composite(out, im, self.object_mask.resize(im.size))
        elif not self.show_original.get() and self.roi:
            mask=Image.new("L",im.size,0); d=ImageDraw.Draw(mask); d.rectangle(tuple(int(v*s) for v,s in zip(self.roi,(im.width,im.height,im.width,im.height))),fill=255); out=Image.composite(out,im,mask)
        self.preview = ImageTk.PhotoImage(out); self.preview_label.delete("all"); self.preview_label.create_image(0,0,image=self.preview,anchor="nw"); self.display_size=im.size
        if self.roi:
            x0,y0,x1,y1=self.roi; self.preview_label.create_rectangle(x0*im.width,y0*im.height,x1*im.width,y1*im.height,outline="#55d6ff",width=2,tags="roi")
    def save_image(self):
        if self.source is None: return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg"), ("WebP", "*.webp")])
        if not path: return
        try:
            out = process_image(self.source, self._settings())
            if self.object_mask is not None:
                out = Image.composite(out, self.source, self.object_mask.resize(self.source.size))
            # JPEG has no alpha channel; flatten only for that export format.
            if os.path.splitext(path)[1].lower() in (".jpg", ".jpeg"):
                out = out.convert("RGB")
            out.save(path)
            self._set_status("Saved " + os.path.basename(path))
        except Exception as exc: messagebox.showerror("Save failed", str(exc))


def smoke_test() -> None:
    image = Image.new("RGBA", (64, 48), (120, 130, 140, 255)); image.putpixel((10, 10), (240, 20, 30, 255))
    settings = EnhanceSettings(contrast=25, highlights=-15, shadows=20, detail=20, blend_mode="Screen", opacity=65, passes=2)
    output = process_image(image, settings)
    assert output.size == image.size and output.mode == "RGBA"
    print("smoke test passed: pipeline produced", output.size, output.mode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="General-purpose image enhancement preview tool")
    parser.add_argument("--smoke-test", action="store_true", help="run a headless processing check")
    args = parser.parse_args()
    if args.smoke_test: smoke_test()
    else: App().mainloop()
