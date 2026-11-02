"""Session-only normalized analysis, notes and immutable batch/export snapshots."""

from dataclasses import replace
import json

from comfyui_support_tools.shared.contracts.inspector_contracts import (
    ActionRequest,
    ExportSettings,
    InspectorStatus,
    MediaExportRecord,
    MediaNotes,
    TaggerSettings,
)
from comfyui_support_tools.applications.main_gui.process.processing.media_actions import (
    action_options,
    validate_settings,
)
from comfyui_support_tools.applications.main_gui.process.processing.tag_result import (
    parse_tag_result,
)

STRING_TUPLE_FIELDS = ("content_tags", "style_tags", "character_tags", "copyright_tags")
TEXT_FIELDS = ("prompt", "negative_prompt", "character", "dataset", "rating", "caption")


# {
# 責務: [InspectorState: Tagger settings、選択、notes、token付きaction状態をsession内で保持する]
# フィールド: [settings/models/selection, item notes+versions, busy/ready/message, request token, success/failure counters]
# }
class InspectorState:
    # {
    #   責務: [__init__: Inspectorをdefault Tagger stateと空session cacheで初期化する]
    #   処理: [selection/notes/version/job counters/tokenを空にし未接続statusを設定する]
    #   引数: [self: session state]
    #   戻り値: [なし]
    # }
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

    # {
    #   責務: [configure: idle時だけTaggerSettingsを検証してcurrent stateへ適用する]
    #   処理: [busyを拒否しsettings検証、URL/backend変更時model cache clear、ready/messageを更新する]
    #   引数: [self: state, settings: TaggerSettings]
    #   戻り値: [なし]
    #   エラー: [ValueError: action実行中またはsettings不正]
    # }
    def configure(self, settings):
        if self.busy:
            raise ValueError("処理中はAPI設定を変更できません")
        validate_settings(settings)
        if (settings.url, settings.backend) != (self.settings.url, self.settings.backend):
            self.models = ()
        self.settings = settings
        self.ready = settings.model in self.models
        self.message = "接続確認済み" if self.ready else "API未確認 / モデルを確認してください"

    # {
    #   責務: [select: 60件以下のunique MediaItem selectionを保持する]
    #   処理: [item version変更時は古いnotesを破棄しselectionを更新する]
    #   引数: [self: state, items: selected MediaItem iterable]
    #   戻り値: [なし]
    #   エラー: [ValueError: selectionが60件超過またはID重複]
    #   副作用: [version mismatchのsession notes cacheを削除する]
    # }
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

    # {
    #   責務: [options: selection/settings/ready/busyに基づくaction availabilityを作る]
    #   処理: [action_optionsへcurrent stateを渡す]
    #   引数: [self: state]
    #   戻り値: [ActionAvailability tuple]
    # }
    def options(self):
        return action_options(self.selection, self.ready, self.busy)

    # {
    #   責務: [current_notes: 単一選択時のnotesを返しmulti/empty selectionならNoneにする]
    #   処理: [notes cacheを引き、未登録itemにはempty MediaNotesを返す]
    #   引数: [self: state]
    #   戻り値: [MediaNotesまたはNone]
    # }
    def current_notes(self):
        if len(self.selection) != 1:
            return None
        return self.notes.get(self.selection[0].id, MediaNotes())

    # {
    #   責務: [save_notes: itemを変更しないsession-only notesとして検証後保存する]
    #   処理: [idle single-image条件、tuple/text上限、manual edit時のscore/backend resetを適用する]
    #   引数: [self: state, notes: updated MediaNotes]
    #   戻り値: [なし]
    #   エラー: [ValueError: selection/busy/text/field limits違反]
    #   副作用: [session notes/version cacheとstatus messageを更新する。source fileは書かない]
    # }
    def save_notes(self, notes):
        if self.busy or len(self.selection) != 1 or self.selection[0].kind != "image":
            raise ValueError("編集は単一選択・Action停止中のみ可能です")
        tuple_values = []
        for field in STRING_TUPLE_FIELDS:
            values = getattr(notes, field)
            if len(values) > 2000:
                raise ValueError(f"{field} が多すぎます")
            tuple_values.extend(values)
        text_values = [getattr(notes, field) for field in TEXT_FIELDS]
        all_text = tuple_values + text_values
        if (
            any(not isinstance(value, str) or len(value) > 8192 for value in all_text)
            or sum(len(value) for value in all_text) > 49152
        ):
            raise ValueError("メモが長すぎます（field上限8192文字）")

        previous = self.notes.get(self.selection[0].id, MediaNotes())
        updates = {}
        if notes.content_tags != previous.content_tags:
            updates["content_scores"] = ()
        if notes.character_tags != previous.character_tags:
            updates["character_scores"] = ()
        if notes.rating != previous.rating:
            updates["rating_scores"] = ()
        analysis_fields = (
            notes.content_tags != previous.content_tags
            or notes.character_tags != previous.character_tags
            or notes.copyright_tags != previous.copyright_tags
            or notes.rating != previous.rating
            or notes.caption != previous.caption
        )
        if analysis_fields:
            updates["tagger_backend"] = "manual-edit"
            updates["tagger_model"] = ""
        if updates:
            notes = replace(notes, **updates)
        self._store(self.selection[0], notes)
        self.message = "セッション内に反映しました。元ファイルへは保存しません"

    # {
    #   責務: [_store: item notesと検査基準となるsize/mtime versionをsession cacheへ保存する]
    #   処理: [cache件数上限を守りitem.idをkeyとしてnotes/versionを更新する]
    #   引数: [self: state, item: source MediaItem, notes: normalized/manual notes]
    #   戻り値: [なし]
    #   エラー: [ValueError: 新規cache entryで4096 item上限超過]
    # }
    def _store(self, item, notes):
        key = item.id
        if key not in self.notes and len(self.notes) >= 4096:
            raise ValueError("セッションのメモ上限4096件に到達しました")
        self.notes[key] = notes
        self.versions[key] = (item.size, item.modified_ns)

    # {
    #   責務: [begin: probe/tag actionの入力を検証しtokenized ActionRequestを作る]
    #   処理: [busy/setting/action availabilityを確認しprobeならmodel stateをresetしてstatusを開始状態にする]
    #   引数: [self: state, kind: probeまたはavailable action ID]
    #   戻り値: [ActionRequest: settings/selection snapshotとnew token]
    #   エラー: [ValueError: action実行中、setting不正、action unavailable/unknown]
    #   副作用: [probe時model cacheを消しbusy/message/token/request stateを更新する]
    # }
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
        self.request = ActionRequest(
            self.token,
            kind,
            self.settings,
            self.selection if kind != "probe" else (),
        )
        self._begin_status(
            "接続確認中…" if kind == "probe" else f"タグ付け中: 0/{len(self.selection)}"
        )
        return self.request

    # {
    #   責務: [begin_export: idle image selectionのimmutable export snapshotを作る]
    #   処理: [1..60 imageとoutput optionを検証しcurrent notesでMediaExportRecordを作る]
    #   引数: [self: state, settings: ExportSettings]
    #   戻り値: [ActionRequest: export kind、selection、notes snapshot、new token]
    #   エラー: [ValueError: busy、image selection不正、または出力形式未指定]
    #   副作用: [request token/busy/message stateを更新する]
    # }
    def begin_export(self, settings: ExportSettings):
        if self.busy:
            raise ValueError("Action実行中です")
        if (
            not self.selection
            or len(self.selection) > 60
            or any(item.kind != "image" for item in self.selection)
        ):
            raise ValueError("Exportは画像1〜60件を選択してください")
        if not (settings.caption_sidecar or settings.metadata_sidecar or settings.batch_txt_path):
            raise ValueError("少なくとも1つの出力形式を選択してください")
        records = tuple(
            MediaExportRecord(item, self.notes.get(item.id, MediaNotes()))
            for item in self.selection
        )
        self.token += 1
        self.request = ActionRequest(
            self.token,
            "export",
            self.settings,
            self.selection,
            settings,
            records,
        )
        self._begin_status(f"Export準備中: {len(records)}件")
        return self.request

    # {
    #   責務: [_begin_status: operation開始に合わせてbusy/counters/messageをresetする]
    #   処理: [busy true、success/failure zero、finished IDs empty、messageを設定する]
    #   引数: [self: state, message: visible progress text]
    #   戻り値: [なし]
    # }
    def _begin_status(self, message):
        self.busy = True
        self.successes = self.failures = 0
        self.finished = set()
        self.message = message

    # {
    #   責務: [failed_start: data worker start失敗後にbusyを解除し再試行案内を表示する]
    #   処理: [busy falseとfailure messageに更新する]
    #   引数: [self: state]
    #   戻り値: [なし]
    # }
    def failed_start(self):
        self.busy = False
        self.message = "Actionを開始できませんでした。前の処理終了を待って再試行してください"

    # {
    #   責務: [accept: current token/actionのworker eventsをnotes/statusへ反映する]
    #   処理: [stale eventsを無視し、models/result/export/error/done kind別にvalidationとstate transitionを行う]
    #   引数: [self: state, events: ActionEvent iterable]
    #   戻り値: [tuple[str,...]: UIへ通知するmessage fragments]
    #   副作用: [model/notes/cache/busy/counters/statusを更新する]
    # }
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
                self.message = (
                    "接続確認済み"
                    if self.ready
                    else "指定モデルは利用不可です。モデルを選択してください"
                )
            elif event.kind == "result" and event.item in self.request.items:
                if event.item.id in self.finished:
                    continue
                self.finished.add(event.item.id)
                try:
                    if event.failed:
                        raise ValueError(event.message)
                    result = parse_tag_result(
                        json.loads(event.message),
                        self.request.settings.threshold,
                        self.request.settings.character_threshold,
                        self.request.settings.backend,
                        self.request.settings.url,
                        self.request.settings.model,
                    )
                    current = next(
                        (item for item in self.selection if item.id == event.item.id), event.item
                    )
                    if (current.size, current.modified_ns) != (
                        event.item.size,
                        event.item.modified_ns,
                    ):
                        raise ValueError(
                            "選択中のファイルは更新済みです。古いTag結果は反映しません"
                        )
                    previous = self.notes.get(event.item.id, MediaNotes())
                    updated = replace(
                        previous,
                        content_tags=result.content_tags,
                        character_tags=result.character_tags,
                        copyright_tags=result.copyright_tags,
                        rating=result.rating,
                        caption=result.caption,
                        tagger_backend=result.backend,
                        tagger_model=result.model,
                        content_scores=result.content_scores,
                        character_scores=result.character_scores,
                        rating_scores=result.rating_scores,
                    )
                    self._store(event.item, updated)
                    self.successes += 1
                    messages.append(
                        f"Tag: {event.item.name} / {len(result.content_tags)} general"
                        + (f" / rating={result.rating}" if result.rating else "")
                    )
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    self.failures += 1
                    messages.append(f"Tag失敗: {event.item.name} / {exc}"[:400])
                self.message = (
                    f"Tag: 成功{self.successes} / 失敗{self.failures} / 全{len(self.request.items)}"
                )
            elif event.kind == "exported":
                self.message = event.message
                messages.append(event.message)
            elif event.kind == "error":
                if self.request.kind in ("probe", "tag"):
                    self.ready = False
                self.message = event.message
                messages.append(event.message)
            elif event.kind == "done":
                self.busy = False
                if self.request.kind == "tag":
                    remaining = len(self.request.items) - len(self.finished)
                    self.message = f"{event.message}: 成功{self.successes} / 失敗{self.failures} / 未処理{remaining}"
                elif self.request.kind == "probe" and event.message != "完了":
                    self.ready = False
                    self.message = event.message
                elif self.request.kind == "export" and event.message != "完了":
                    self.message = event.message
                messages.append(self.message)
        return tuple(messages)

    # {
    #   責務: [status: current session valuesをInspectorStatus immutable contractへ投影する]
    #   処理: [settings/models/busy/ready/messageをsnapshotへ渡す]
    #   引数: [self: state]
    #   戻り値: [InspectorStatus]
    # }
    def status(self):
        return InspectorStatus(self.settings, self.models, self.busy, self.ready, self.message)
