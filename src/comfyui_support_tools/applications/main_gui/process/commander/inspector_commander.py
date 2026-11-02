"""Route commands; session rules and IO belong to their Processing components."""

from comfyui_support_tools.applications.main_gui.process.processing.inspector_state import (
    InspectorState,
)
from comfyui_support_tools.applications.main_gui.process.messenger.action_data_messenger import (
    ActionDataRequests,
)


# {
# 責務: [InspectorCommander: InspectorStateを更新しActionDataRequestsと非同期処理を調整する]
# フィールド: [_state: Process state model, _data: ActionIO request boundary]
# }
class InspectorCommander:
    # {
    #   責務: [__init__: Inspector stateとAction data request boundaryを接続する]
    #   処理: [stateとdataを各Inspector command用delegateとして保存する]
    #   引数: [self: commander, state: InspectorState, data: ActionDataRequests]
    #   戻り値: [なし]
    # }
    def __init__(self, state: InspectorState, data: ActionDataRequests):
        self._state = state
        self._data = data

    # {
    #   責務: [configure: Tagger settingsをInspectorStateへ適用する]
    #   処理: [state.configureへdelegateする]
    #   引数: [self: commander, settings: TaggerSettings]
    #   戻り値: [state.configure result]
    # }
    def configure(self, settings):
        return self._state.configure(settings)

    # {
    #   責務: [select: Inspectorで処理対象とするmedia itemsを設定する]
    #   処理: [state.selectへ選択itemsを渡す]
    #   引数: [self: commander, items: MediaItem selection]
    #   戻り値: [state.select result]
    # }
    def select(self, items):
        return self._state.select(items)

    # {
    #   責務: [options: 現在のselection/settingsから利用可能action optionsを得る]
    #   処理: [state.optionsを返す]
    #   引数: [self: commander]
    #   戻り値: [ActionAvailability sequence]
    # }
    def options(self):
        return self._state.options()

    # {
    #   責務: [notes: selected itemのcurrent notes mappingを取得する]
    #   処理: [state.current_notesへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [current media notes]
    # }
    def notes(self):
        return self._state.current_notes()

    # {
    #   責務: [save_notes: selected itemへMediaNotesを保存する]
    #   処理: [state.save_notesへnotesを渡す]
    #   引数: [self: commander, notes: updated MediaNotes]
    #   戻り値: [state save result]
    # }
    def save_notes(self, notes):
        return self._state.save_notes(notes)

    # {
    #   責務: [status: Inspector settings/busy/ready/status message snapshotを返す]
    #   処理: [state.statusを呼ぶ]
    #   引数: [self: commander]
    #   戻り値: [InspectorStatus contract]
    # }
    def status(self):
        return self._state.status()

    # {
    #   責務: [start: 指定kindのInspector requestを組み立てData workerへ開始依頼する]
    #   処理: [state.beginでrequestを作り_start_requestへ渡す]
    #   引数: [self: commander, kind: probeまたはtag action]
    #   戻り値: [なし]
    #   エラー: [state validationまたはdata start error]
    #   副作用: [ActionIO workerを開始する]
    # }
    def start(self, kind):
        return self._start_request(self._state.begin(kind))

    # {
    #   責務: [export: ExportSettingsに従うInspector export requestを開始する]
    #   処理: [state.begin_exportでrecords/requestを作って_start_requestへ渡す]
    #   引数: [self: commander, settings: ExportSettings]
    #   戻り値: [なし]
    #   エラー: [state validationまたはdata start error]
    #   副作用: [ActionIO export workerを開始する]
    # }
    def export(self, settings):
        return self._start_request(self._state.begin_export(settings))

    # {
    #   責務: [_start_request: data start failure時にInspector busy stateをrollbackする]
    #   処理: [data.startを試し、exception時failed_startを呼んで元exceptionを再送出する]
    #   引数: [self: commander, request: ActionRequest]
    #   戻り値: [なし]
    #   エラー: [data.start original exception]
    #   副作用: [start失敗時にInspectorStateを更新する]
    # }
    def _start_request(self, request):
        try:
            self._data.start(request)
        except Exception:
            self._state.failed_start()
            raise

    # {
    #   責務: [poll: pending ActionEventをDataから取得しInspectorStateへ適用する]
    #   処理: [data.pollのeventsをstate.acceptへ渡す]
    #   引数: [self: commander]
    #   戻り値: [state.accept change/result]
    # }
    def poll(self):
        return self._state.accept(self._data.poll())

    # {
    #   責務: [cancel: active ActionIO operationの停止を依頼する]
    #   処理: [data.cancelへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [data cancel result]
    #   副作用: [worker cancellationを要求する]
    # }
    def cancel(self):
        return self._data.cancel()

    # {
    #   責務: [close: Inspector Data worker boundaryを閉じる]
    #   処理: [data.closeへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [close result]
    #   副作用: [underlying ActionIO resourcesを閉じる]
    # }
    def close(self):
        return self._data.close()
