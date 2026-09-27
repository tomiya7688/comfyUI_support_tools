"""Inspector fields, Media Actions and explicit analysis export."""
from dataclasses import asdict, replace
import tkinter as tk
from tkinter import ttk, messagebox

from comfyui_support_tools.shared.contracts.inspector_contracts import MediaNotes
from comfyui_support_tools.shared.contracts.tagger_backend import backend_label
from comfyui_support_tools.applications.main_gui.ui.commander.inspector_commander import InspectorUiCommander
from comfyui_support_tools.applications.main_gui.ui.processing.export_dialog import ExportDialog
from comfyui_support_tools.applications.main_gui.ui.processing.tagger_settings_dialog import TaggerSettingsDialog

NOTE_FIELDS = (
    ("content_tags", "内容Tags", "Tags"),
    ("style_tags", "Style（別field）", "Tags"),
    ("character_tags", "Character Tags", "Tag Meta"),
    ("copyright_tags", "Copyright Tags", "Tag Meta"),
    ("rating", "Rating", "Tag Meta"),
    ("caption", "Caption / image-to-text", "Tag Meta"),
    ("prompt", "Prompt", "Prompt"),
    ("negative_prompt", "Negative Prompt", "Prompt"),
    ("character", "Characterメモ", "メモ"),
    ("dataset", "Dataset / LoRAメモ", "メモ"),
)
TUPLE_FIELDS = {"content_tags", "style_tags", "character_tags", "copyright_tags"}


class InspectorPanel(ttk.Frame):
    def __init__(self, master, commander: InspectorUiCommander, log):
        super().__init__(master)
        self.commander = commander
        self.log = log
        self.selection = ()
        self._closed = False
        self._last_notes = None
        self._settings_window = None
        self._export_window = None
        self._pending_edits = False
        self._editing_fields = False
        self.status_text = tk.StringVar(self)
        self.reason_text = tk.StringVar(self)
        self.analysis_meta = tk.StringVar(self, value="Tagger result: —")
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
        ttk.Button(self, text="Tagger Backend / API設定", command=self.open_settings).pack(fill="x", pady=4)
        self.cancel_button = ttk.Button(self, text="停止要求", command=self.cancel)
        self.cancel_button.pack(fill="x")
        ttk.Label(self, textvariable=self.status_text, wraplength=195).pack(fill="x", pady=4)
        ttk.Label(self, textvariable=self.analysis_meta, wraplength=195).pack(fill="x", pady=(0, 4))
        self.notes_hint = ttk.Label(self, text="", wraplength=195)
        self.notes_hint.pack(fill="x", pady=4)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="x")
        pages = {}
        for page_name in ("Tags", "Tag Meta", "Prompt", "メモ"):
            page = ttk.Frame(notebook)
            notebook.add(page, text=page_name)
            pages[page_name] = page

        self.fields = {}
        for key, label, page_name in NOTE_FIELDS:
            page = pages[page_name]
            ttk.Label(page, text=label).pack(anchor="w")
            field = tk.Text(page, height=2, width=22, wrap="word", undo=True)
            field.pack(fill="x", pady=(0, 4))
            field.bind("<<Modified>>", self._modified, add=True)
            self.fields[key] = field

        self.save_button = ttk.Button(self, text="メモをセッションに反映", command=self.save_notes)
        self.save_button.pack(fill="x", pady=4)
        self.export_button = ttk.Button(self, text="結果をTXT / metadataへExport", command=self.open_export)
        self.export_button.pack(fill="x", pady=4)
        ttk.Label(
            self,
            text="Exportは明示操作のみ。元画像は変更せず、既存sidecarは既定で上書きしません。",
            wraplength=195,
        ).pack(fill="x", pady=4)

        self.refresh(force_notes=True)
        self._after = self.after(70, self._poll)
        self.bind("<Destroy>", self._destroyed, add=True)

    def select(self, items):
        values = tuple(items)
        if values != self.selection:
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
            current = self.commander.notes() or MediaNotes()
            values = {key: field.get("1.0", "end-1c") for key, field in self.fields.items()}
            for key in TUPLE_FIELDS:
                values[key] = tuple(dict.fromkeys(
                    word.strip()
                    for word in values[key].replace("\n", ",").split(",")
                    if word.strip()
                ))
            self.commander.save_notes(replace(current, **values))
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
        exportable = bool(self.selection) and len(self.selection) <= 60 and all(
            item.kind == "image" for item in self.selection
        ) and not status.busy
        self.export_button.configure(state="normal" if exportable else "disabled")

        if notes and notes.tagger_backend:
            label = backend_label(notes.tagger_backend)
            self.analysis_meta.set(f"Tagger result: {label} / {notes.tagger_model or 'model不明'}")
        else:
            self.analysis_meta.set("Tagger result: —")

        if not self.selection:
            hint = "メディア未選択"
        elif len(self.selection) > 1:
            hint = f"{len(self.selection)}件選択。Tag/Exportはbatch、メモ編集は単一画像のみ。"
        elif self.selection[0].kind == "video":
            hint = "動画は画像Tag/Export対象外。Video Actionは#223側で移行します。"
        else:
            hint = "Content / Rating / Style / Captionを別fieldで保持します。"
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
        message = (
            f"{len(snapshot)}枚の画像（元の画像データ・埋込情報を含む）を送信します。\n\n"
            f"Backend: {backend_label(settings.backend, settings.url)}\n"
            f"宛先: {settings.url}\nモデル: {settings.model}\n\n"
            "結果はcontent / character / copyright / rating / captionへ正規化し、Styleは混在させません。"
        )
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

    def open_export(self):
        if self._pending_edits:
            self.log("未反映メモを先にセッションへ反映してください。")
            return
        if self._export_window and self._export_window.winfo_exists():
            self._export_window.lift()
            return
        self._export_window = ExportDialog(self, self.export_results, self.log)

    def export_results(self, settings):
        snapshot = self.selection
        if not snapshot or any(item.kind != "image" for item in snapshot):
            self.log("Exportは画像を選択してください")
            return False
        outputs = []
        if settings.caption_sidecar:
            outputs.append("caption .txt sidecar")
        if settings.metadata_sidecar:
            outputs.append(".kadoka.json metadata")
        if settings.batch_txt_path:
            outputs.append(f"batch TXT: {settings.batch_txt_path}")
        message = (
            f"{len(snapshot)}件の解析結果を書き出します。\n\n"
            + "\n".join(outputs)
            + f"\nStyleをcaptionへ連結: {'はい' if settings.include_style_in_caption else 'いいえ'}"
            + f"\n既存ファイル上書き: {'許可' if settings.overwrite else '禁止'}"
        )
        if not messagebox.askyesno("Analysis結果のExport確認", message, parent=self):
            return False
        if snapshot != self.selection or self._pending_edits:
            self.log("選択またはメモ状態が変わりました。Exportをやり直してください。")
            return False
        try:
            self.commander.export(settings)
            self.refresh()
            return True
        except (ValueError, OSError) as exc:
            self.log(str(exc))
            return False

    def fill_menu(self, menu):
        menu.delete(0, "end")
        for option in self.commander.options():
            label = option.definition.label + (" — " + option.reason if option.reason else "")
            menu.add_command(
                label=label,
                state="normal" if option.enabled else "disabled",
                command=lambda key=option.definition.id: self.run_action(key),
            )

    def open_settings(self):
        if self._settings_window and self._settings_window.winfo_exists():
            self._settings_window.lift()
            return
        self._settings_window = TaggerSettingsDialog(self, self.commander, self.log)

    def cancel(self):
        self.commander.cancel()
        self.log("停止要求: 実行中のHTTP/ファイルIO完了後に停止します")

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
