"""Explicit URL/model controls; opening this dialog makes no network request."""
import tkinter as tk
from tkinter import ttk
from comfyui_support_tools.shared.contracts.inspector_contracts import TaggerSettings


class TaggerSettingsDialog(tk.Toplevel):
    def __init__(self, parent, commander, log):
        super().__init__(parent)
        self.commander, self.log = commander, log
        self.title("Tagger HTTP API設定")
        self.transient(parent.winfo_toplevel())
        self.geometry("640x360")
        self.minsize(500, 360)
        self._seen_models = ()
        self._last_status = None
        settings = commander.status().settings
        self.values = {}
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        for key, label in (("url", "API URL"), ("model", "モデル"), ("threshold", "Tag閾値"),
                           ("character_threshold", "Character閾値"), ("timeout", "Timeout秒")):
            row = ttk.Frame(body)
            row.pack(fill="x", pady=4)
            ttk.Label(row, text=label, width=16).pack(side="left")
            variable = tk.StringVar(self, value=str(getattr(settings, key)))
            self.values[key] = variable
            entry = ttk.Combobox(row, textvariable=variable) if key == "model" else ttk.Entry(row, textvariable=variable)
            entry.pack(side="left", fill="x", expand=True)
            if key == "model":
                self.models = entry
        ttk.Label(body, text="例: http://127.0.0.1:7861/pixai/v1/interrogate\n接続確認はモデル一覧GETのみ。画像送信は実行時に確認します。\n設定とメモはWorkspace内のみ保持。サービスの自動起動・依存の導入はしません。",
                  wraplength=580).pack(anchor="w", pady=8)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        self.apply_button = ttk.Button(buttons, text="設定を反映", command=self.apply)
        self.apply_button.pack(side="left")
        self.probe_button = ttk.Button(buttons, text="接続確認・モデル一覧", command=self.probe)
        self.probe_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="閉じる", command=self.destroy).pack(side="right")
        self.message = tk.StringVar(self)
        ttk.Label(body, textvariable=self.message, wraplength=580).pack(anchor="w", pady=8)
        self.refresh(commander.status())

    def apply(self):
        try:
            values = {key: value.get().strip() for key, value in self.values.items()}
            for key in ("threshold", "character_threshold", "timeout"):
                values[key] = float(values[key])
            self.commander.configure(TaggerSettings(**values))
            self.refresh(self.commander.status())
            return True
        except (ValueError, TypeError) as exc:
            self.message.set(str(exc))
            self.log(str(exc))
            return False

    def probe(self):
        if self.apply():
            try:
                self.commander.start("probe")
                self.refresh(self.commander.status())
            except ValueError as exc:
                self.message.set(str(exc))

    def refresh(self, status):
        self.apply_button.configure(state="disabled" if status.busy else "normal")
        self.probe_button.configure(state="disabled" if status.busy else "normal")
        if status.models != self._seen_models:
            self.models.configure(values=status.models)
            if not self.values["model"].get():
                self.values["model"].set(status.settings.model)
            self._seen_models = status.models
        if status != self._last_status:
            self.message.set(status.message)
            self._last_status = status
