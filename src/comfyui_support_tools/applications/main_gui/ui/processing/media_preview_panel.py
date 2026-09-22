"""Basic Inspector preview only; editable Actions belong to issue #220."""
import base64
import math
import tkinter as tk
from tkinter import ttk


class MediaPreviewPanel(ttk.Frame):
    def __init__(self, master, on_seek):
        super().__init__(master)
        self.on_seek = on_seek
        self.item_id = None
        self.photo = None
        self._seek_after = None
        self._setting = False
        self.image = ttk.Label(self, text="メディア未選択")
        self.image.pack(anchor="center", pady=8)
        self.details = ttk.Label(self, text="", wraplength=210)
        self.details.pack(anchor="w")
        self.seek_frame = ttk.Frame(self)
        ttk.Label(self.seek_frame, text="動画: 静止フレーム位置", wraplength=200).pack(anchor="w")
        self.position = tk.DoubleVar(self, value=0)
        ttk.Scale(self.seek_frame, from_=0, to=100, variable=self.position,
                  command=self._schedule_seek).pack(fill="x")
        ttk.Label(self.seek_frame, text="連続再生・音声再生は未対応", wraplength=200).pack(anchor="w")
        self.bind("<Destroy>", self._destroyed, add=True)

    def select(self, items):
        self.item_id = items[0].id if items else None
        self.photo = None
        self.image.configure(image="", text="プレビュー読込中…" if items else "メディア未選択")
        self.details.configure(text="")
        if self._seek_after:
            self.after_cancel(self._seek_after)
            self._seek_after = None
        self._setting = True
        self.position.set(0)
        self._setting = False
        self.seek_frame.pack_forget()
        if items and items[0].kind == "video":
            self.seek_frame.pack(fill="x", pady=8)

    def render(self, preview):
        if preview.item_id != self.item_id:
            return
        if preview.error:
            self.image.configure(image="", text="プレビューなし")
            self.details.configure(text=preview.error[:300])
            return
        photo = tk.PhotoImage(master=self, data=base64.b64encode(preview.png))
        scale = max(1, math.ceil(photo.width()/210), math.ceil(photo.height()/240))
        self.photo = photo.subsample(scale, scale)
        self.image.configure(image=self.photo, text="")
        duration = f" / 約 {preview.duration:.1f} 秒" if preview.duration else ""
        self.details.configure(text=f"{preview.width} × {preview.height}{duration}")

    def _schedule_seek(self, _value):
        if self._setting or not self.item_id:
            return
        if self._seek_after:
            self.after_cancel(self._seek_after)
        self._seek_after = self.after(200, self._seek)

    def _seek(self):
        self._seek_after = None
        self.image.configure(text="位置を読込中…")
        self.on_seek(self.position.get()/100)

    def _destroyed(self, event):
        if event.widget is self and self._seek_after:
            self.after_cancel(self._seek_after)
