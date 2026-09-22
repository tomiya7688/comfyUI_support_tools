"""Inspector notes and Action entry points. Network/validation live behind UPD."""
from dataclasses import asdict
import tkinter as tk
from tkinter import ttk, messagebox

from comfyui_support_tools.shared.contracts.inspector_contracts import MediaNotes
from comfyui_support_tools.applications.main_gui.ui.commander.inspector_commander import InspectorUiCommander
from comfyui_support_tools.applications.main_gui.ui.processing.tagger_settings_dialog import TaggerSettingsDialog

NOTE_FIELDS = (("content_tags", "内容Tags"), ("style_tags", "Style（別field）"),
               ("prompt", "Prompt"), ("negative_prompt", "Negative Prompt"),
               ("character", "Characterメモ"), ("dataset", "Dataset / LoRAメモ"))


class InspectorPanel(ttk.Frame):
    def __init__(self, master, commander: InspectorUiCommander, log):
        super().__init__(master)
        self.commander = commander
        self.log = log
        self.selection = ()
        self._closed = False
        self._last_notes = None
        self._settings_window = None
        self._pending_edits = False
        self._editing_fields = False
        self.status_text = tk.StringVar(self)
        self.reason_text = tk.StringVar(self)
        self.action = tk.StringVar(self, value="Tag / 内容タグ付け")
        ttk.Label(self, text="MEDIA ACTION", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(8, 4))
        choices = tuple(value.definition.label for value in commander.options())
        combo = ttk.Combobox(self, textvariable=self.action, values=choices, state="readonly", width=21)
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        self.run_button = ttk.Button(self, text="選択へ実行", command=self.run_selected)
        self.run_button.pack(fill="x", pady=4)
        self.reason = ttk.Label(self, textvariable=self.reason_text, wraplength=195)
        self.reason.pack(fill="x")
        ttk.Button(self, text="Tagger API設定・接続確認", command=self.open_settings).pack(fill="x", pady=4)
        self.cancel_button = ttk.Button(self, text="停止要求", command=self.cancel)
        self.cancel_button.pack(fill="x")
        ttk.Label(self, textvariable=self.status_text, wraplength=195).pack(fill="x", pady=4)
        self.notes_hint = ttk.Label(self, text="", wraplength=195)
        self.notes_hint.pack(fill="x", pady=4)
        notebook = ttk.Notebook(self)
        notebook.pack(fill="x")
        pages = []
        for label in ("Tags", "Prompt", "メモ"):
            page = ttk.Frame(notebook)
            notebook.add(page, text=label)
            pages.append(page)
        self.fields = {}
        for index, (key, label) in enumerate(NOTE_FIELDS):
            page = pages[index // 2]
            ttk.Label(page, text=label).pack(anchor="w")
            field = tk.Text(page, height=2, width=22, wrap="word", undo=True)
            field.pack(fill="x", pady=(0, 4))
            field.bind("<<Modified>>", self._modified, add=True)
            self.fields[key] = field
        self.save_button = ttk.Button(self, text="メモをセッションに反映", command=self.save_notes)
        self.save_button.pack(fill="x", pady=4)
        ttk.Label(self, text="元ファイルへの保存なし。生成設定・学習設定の実行は未対応。", wraplength=195).pack(fill="x", pady=4)
        self.refresh(force_notes=True)
        self._after = self.after(70, self._poll)
        self.bind("<Destroy>", self._destroyed, add=True)

    def select(self, items):
        values = tuple(items)
        if values != self.selection:
            # Explicit save: do not accidentally assign edits for A to newly selected B.
            if self._pending_edits:
                self.log("未反映のInspectorメモを破棄しました。選択前に「セッションに反映」を使用してください。")
            self._pending_edits = False
            self.selection = values
            self.commander.select(values)
            self.refresh(force_notes=True)

    def _modified(self, event):
        widget = event.widget
        if widget.edit_modified():
            if not self._editing_fields:
                self._pending_edits = True
            widget.edit_modified(False)

    def _set_notes(self, notes):
        self._editing_fields = True
        values = asdict(notes or MediaNotes())
        for key, field in self.fields.items():
            value = values[key]
            field.configure(state="normal")
            field.delete("1.0", "end")
            field.insert("1.0", ", ".join(value) if isinstance(value, tuple) else value)
            field.edit_modified(False)
            field.edit_reset()
        self._editing_fields = False
        self._pending_edits = False
        self._last_notes = notes

    def save_notes(self):
        try:
            values = {key: field.get("1.0", "end-1c") for key, field in self.fields.items()}
            for key in ("content_tags", "style_tags"):
                values[key] = tuple(dict.fromkeys(word.strip() for word in values[key].replace("\n", ",").split(",") if word.strip()))
            self.commander.save_notes(MediaNotes(**values))
            self._pending_edits = False
            self.refresh(force_notes=True)
        except (ValueError, TypeError) as exc:
            self.log(str(exc))

    def refresh(self, force_notes=False):
        status = self.commander.status()
        options = self.commander.options()
        option = next((value for value in options if value.definition.label == self.action.get()), options[0])
        self.reason_text.set(option.reason or "画像を設定先APIへ送信します。実行前に宛先と件数を確認します。")
        self.run_button.configure(state="normal" if option.enabled else "disabled")
        self.cancel_button.configure(state="normal" if status.busy else "disabled")
        self.status_text.set(status.message)
        notes = self.commander.notes()
        if force_notes or (not self._pending_edits and notes != self._last_notes):
            self._set_notes(notes)
        editable = len(self.selection) == 1 and self.selection[0].kind == "image" and not status.busy
        for field in self.fields.values():
            field.configure(state="normal" if editable else "disabled")
        self.save_button.configure(state="normal" if editable else "disabled")
        if not self.selection:
            hint = "メディア未選択"
        elif len(self.selection) > 1:
            hint = f"{len(self.selection)}件選択。Tagは一括実行、メモ編集は単一画像のみ。"
        elif self.selection[0].kind == "video":
            hint = "動画情報はプレビュー下に表示。画像用Tag・生成Actionは対象外。"
        else:
            hint = "Tags / Style / Prompt等は独立したセッションメモ。選択前に反映してください。"
        self.notes_hint.configure(text=hint)
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.refresh(status)

    def run_selected(self):
        option = next(value for value in self.commander.options() if value.definition.label == self.action.get())
        self.run_action(option.definition.id)

    def run_action(self, action_id):
        option = next((value for value in self.commander.options() if value.definition.id == action_id), None)
        if option is None or not option.enabled:
            self.log(option.reason if option else "Unknown Action")
            return
        snapshot = self.selection
        settings = self.commander.status().settings
        message = (f"{len(snapshot)}枚の画像（元の画像データ・埋込情報を含む）を送信します。\n\n"
                   f"宛先: {settings.url}\nモデル: {settings.model}\n\n"
                   "元ファイルは変更しません。内容Tagsは結果で置き換え、Style等は保持します。")
        if self._pending_edits:
            message += "\n未反映のメモがあります。キャンセルして先に反映してください。"
        if not messagebox.askyesno("Tag APIへの送信確認", message, parent=self):
            return
        if snapshot != self.selection or settings != self.commander.status().settings:
            self.log("選択またはAPI設定が変わりました。再度実行してください。")
            return
        if self._pending_edits:
            self.log("未反映メモを先に反映してください。送信は行いませんでした。")
            return
        try:
            self.commander.start(action_id)
            self.refresh()
        except ValueError as exc:
            self.log(str(exc))

    def fill_menu(self, menu):
        menu.delete(0, "end")
        for option in self.commander.options():
            label = option.definition.label + (" — " + option.reason if option.reason else "")
            menu.add_command(label=label, state="normal" if option.enabled else "disabled",
                             command=lambda key=option.definition.id: self.run_action(key))

    def open_settings(self):
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.lift()
            return
        self._settings_window = TaggerSettingsDialog(self, self.commander, self.log)

    def cancel(self):
        self.commander.cancel()
        self.log("停止要求: 実行中のHTTP応答/timeout後に停止します")

    def _poll(self):
        if self._closed:
            return
        for message in self.commander.poll():
            self.log(message)
        self.refresh()
        self._after = self.after(70, self._poll)

    def close(self):
        if not self._closed:
            self._closed = True
            self.after_cancel(self._after)
            self.commander.close()

    def _destroyed(self, event):
        if event.widget is self:
            self.close()
