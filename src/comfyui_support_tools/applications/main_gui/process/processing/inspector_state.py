"""Session-only notes, capability checks and immutable batch snapshots."""
from dataclasses import replace
import json

from comfyui_support_tools.shared.contracts.inspector_contracts import (
    ActionRequest, InspectorStatus, MediaNotes, TaggerSettings,
)
from comfyui_support_tools.applications.main_gui.process.processing.media_actions import action_options, validate_settings
from comfyui_support_tools.applications.main_gui.process.processing.tag_result import parse_tags


class InspectorState:
    def __init__(self):
        self.settings = TaggerSettings()
        self.models = ()
        self.selection = ()
        self.notes = {}
        self.versions = {}
        self.busy = False
        self.ready = False
        self.message = "API未設定 / 自動接続なし"
        self.token = 0
        self.request = None
        self.successes = self.failures = 0
        self.finished = set()

    def configure(self, settings):
        if self.busy:
            raise ValueError("処理中はAPI設定を変更できません")
        validate_settings(settings)
        if settings.url != self.settings.url:
            self.models = ()
        self.settings = settings
        self.ready = settings.model in self.models
        self.message = "接続確認済み" if self.ready else "API未確認 / モデルを確認してください"

    def select(self, items):
        values = tuple(items)
        if len(values) > 60 or len({item.id for item in values}) != len(values):
            raise ValueError("Selection must contain at most 60 unique items")
        for item in values:
            version = (item.size, item.modified_ns)
            if item.id in self.versions and self.versions[item.id] != version:
                self.notes.pop(item.id, None)
                self.versions.pop(item.id, None)
        self.selection = values

    def options(self):
        return action_options(self.selection, self.ready, self.busy)

    def current_notes(self):
        if len(self.selection) != 1:
            return None
        return self.notes.get(self.selection[0].id, MediaNotes())

    def save_notes(self, notes):
        if self.busy or len(self.selection) != 1 or self.selection[0].kind != "image":
            raise ValueError("編集は単一選択・Action停止中のみ可能です")
        fields = (*notes.content_tags, *notes.style_tags, notes.prompt, notes.negative_prompt, notes.character, notes.dataset)
        if (len(notes.content_tags) > 2000 or len(notes.style_tags) > 2000
                or any(not isinstance(text, str) or len(text) > 8192 for text in fields)
                or sum(len(text) for text in fields) > 32768):
            raise ValueError("メモが長すぎます（field上限8192文字）")
        self._store(self.selection[0], notes)
        self.message = "セッション内に反映しました。元ファイルへは保存しません"

    def _store(self, item, notes):
        key = item.id
        if key not in self.notes and len(self.notes) >= 4096:
            raise ValueError("セッションのメモ上限4096件に到達しました")
        self.notes[key] = notes
        self.versions[key] = (item.size, item.modified_ns)

    def begin(self, kind):
        if self.busy:
            raise ValueError("Action実行中です")
        validate_settings(self.settings)
        if kind == "probe":
            self.ready = False
            self.models = ()
        else:
            option = next((value for value in self.options() if value.definition.id == kind), None)
            if option is None or not option.enabled:
                raise ValueError(option.reason if option else "Unknown Action")
        self.token += 1
        self.request = ActionRequest(self.token, kind, self.settings, self.selection if kind != "probe" else ())
        self.busy = True
        self.successes = self.failures = 0
        self.finished = set()
        self.message = "接続確認中…" if kind == "probe" else f"タグ付け中: 0/{len(self.selection)}"
        return self.request

    def failed_start(self):
        self.busy = False
        self.message = "Actionを開始できませんでした。前の処理終了を待って再試行してください"

    def accept(self, events):
        messages = []
        for event in events:
            if event.token != self.token or not self.busy or self.request is None:
                continue
            if event.kind == "models":
                self.models = event.models
                model = self.settings.model or event.models[0]
                self.settings = replace(self.settings, model=model)
                self.ready = model in self.models
                self.message = "接続確認済み" if self.ready else "指定モデルは利用不可です。モデルを選択してください"
            elif event.kind == "result" and event.item in self.request.items:
                if event.item.id in self.finished:
                    continue
                self.finished.add(event.item.id)
                try:
                    if event.failed:
                        raise ValueError(event.message)
                    tags = parse_tags(json.loads(event.message), self.request.settings.threshold)
                    current = next((item for item in self.selection if item.id == event.item.id), event.item)
                    if (current.size, current.modified_ns) != (event.item.size, event.item.modified_ns):
                        raise ValueError("選択中のファイルは更新済みです。古いTag結果は反映しません")
                    previous = self.notes.get(event.item.id, MediaNotes())
                    self._store(event.item, replace(previous, content_tags=tags))
                    self.successes += 1
                    messages.append(f"Tag: {event.item.name} / {len(tags)} tags")
                except (ValueError, TypeError) as exc:
                    self.failures += 1
                    messages.append(f"Tag失敗: {event.item.name} / {exc}"[:400])
                self.message = f"Tag: 成功{self.successes} / 失敗{self.failures} / 全{len(self.request.items)}"
            elif event.kind == "error":
                self.ready = False
                self.message = event.message
                messages.append(event.message)
            elif event.kind == "done":
                self.busy = False
                if self.request.kind != "probe":
                    remaining = len(self.request.items) - len(self.finished)
                    self.message = f"{event.message}: 成功{self.successes} / 失敗{self.failures} / 未処理{remaining}"
                elif event.message != "完了":
                    self.ready = False
                    self.message = event.message
                messages.append(self.message)
        return tuple(messages)

    def status(self):
        return InspectorStatus(self.settings, self.models, self.busy, self.ready, self.message)
