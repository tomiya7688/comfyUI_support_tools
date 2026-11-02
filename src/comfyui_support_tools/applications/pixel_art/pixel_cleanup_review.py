"""Modal review dialog for suggested pixel-art cleanup candidates."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from PIL import ImageDraw, ImageTk

from comfyui_support_tools.shared.pixel_art import (
    PixelArtApplication,
    PixelGrid,
    PixelProject,
    nearest_preview,
)


# {
# 責務: [PixelCleanupReviewDialog: review automatic pixel changes before applying]
# フィールド: [candidate results, active project, preview image, acceptance callback]
# 処理: [display changed pixels and let the user accept one undoable candidate]
# }
class PixelCleanupReviewDialog(tk.Toplevel):
    # {
    # 責務: [__init__: build a modal candidate comparison window]
    # 処理: [create candidate selector, magenta pixel diff, and explicit apply/cancel actions]
    # 引数: [parent, application, project, on_accept: owner and candidate-commit callback]
    # 戻り値: [None: dialog shown]
    # }
    def __init__(
        self,
        parent,
        application: PixelArtApplication,
        project: PixelProject,
        *,
        on_accept: Callable[[PixelGrid], None],
    ) -> None:
        super().__init__(parent)
        self.title("Review cleanup candidates")
        self.transient(parent)
        self.geometry("520x520")
        self._project = project
        self._on_accept = on_accept
        self._candidates = application.cleanup_candidates(project.grid)
        self._selection = tk.IntVar(self, value=0)
        self._photo = None
        self._canvas = tk.Canvas(self, background="#ececec", height=340)
        ttk.Label(self, text="Choose a candidate; no changes are applied until accepted.").pack(
            anchor="w", padx=12, pady=(12, 4)
        )
        self._canvas.pack(fill="both", expand=True, padx=12, pady=6)
        for index, (mode, _result) in enumerate(self._candidates):
            ttk.Radiobutton(
                self,
                text=mode.title(),
                value=index,
                variable=self._selection,
                command=self._show_candidate,
            ).pack(anchor="w", padx=12)
        self._details = tk.StringVar(self)
        ttk.Label(self, textvariable=self._details).pack(anchor="w", padx=12, pady=4)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=10)
        ttk.Button(buttons, text="Apply selected", command=self._accept_candidate).pack(
            side="right"
        )
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=6)
        self.grab_set()
        self._show_candidate()

    # {
    # 責務: [_show_candidate: render selected cleanup and changed-pixel overlay]
    # 処理: [show nearest-neighbor candidate, magenta changes, palette stats, and changed regions]
    # 引数: [None: uses selected candidate]
    # 戻り値: [None: preview updated]
    # }
    def _show_candidate(self) -> None:
        mode, result = self._candidates[self._selection.get()]
        scale = next(
            (
                value
                for value in (8, 4, 1)
                if max(result.grid.width, result.grid.height) * value <= 480
            ),
            1,
        )
        preview = nearest_preview(result.grid, scale)
        overlay = ImageDraw.Draw(preview, "RGBA")
        before = self._project.grid
        for index, (old, new) in enumerate(zip(before.pixels, result.grid.pixels, strict=True)):
            if old == new:
                continue
            x, y = index % before.width, index // before.width
            overlay.rectangle(
                (x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1),
                fill=(255, 0, 220, 128),
            )
        self._photo = ImageTk.PhotoImage(preview)
        self._canvas.delete("all")
        self._canvas.create_image(8, 8, image=self._photo, anchor="nw")
        self._details.set(
            f"{mode}: {result.metadata['changed_pixels']} changed pixels; "
            f"palette {result.metadata['palette_before']} → {result.metadata['palette_after']}; "
            f"regions {result.metadata['changed_regions']} (magenta overlay)"
        )

    # {
    # 責務: [_accept_candidate: append one selected candidate to the project]
    # 処理: [call owner callback only after user presses Apply]
    # 引数: [None: reads selected result]
    # 戻り値: [None: close dialog after successful commit]
    # }
    def _accept_candidate(self) -> None:
        _mode, result = self._candidates[self._selection.get()]
        try:
            self._on_accept(result.grid)
            self.destroy()
        except ValueError as error:
            messagebox.showerror("Pixel cleanup", str(error), parent=self)
