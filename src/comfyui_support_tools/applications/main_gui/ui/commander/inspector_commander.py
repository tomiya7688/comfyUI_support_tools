"""Transport Inspector messages without interpreting their contents."""

from comfyui_support_tools.applications.main_gui.ui.messenger.inspector_messenger import (
    InspectorUiMessenger,
)


# {
# 責務: [InspectorUiCommander: UI向けInspector settings/selection/action APIをmessengerへ転送する]
# フィールド: [_target: InspectorUiMessenger]
# }
class InspectorUiCommander:
    # {
    #   責務: [__init__: InspectorUiMessenger delegateを保持する]
    #   処理: [UI commandを下位messengerへ接続する]
    #   引数: [self: commander, target: InspectorUiMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: InspectorUiMessenger):
        self._target = target

    # {
    #   責務: [configure: UIからTaggerSettingsを更新依頼する]
    #   処理: [target.configureへdelegateする]
    #   引数: [self: commander, settings: TaggerSettings]
    #   戻り値: [configuration result]
    # }
    def configure(self, settings):
        return self._target.configure(settings)

    # {
    #   責務: [select: UI selectionのMediaItemsをInspectorへ伝える]
    #   処理: [target.selectへitemsを渡す]
    #   引数: [self: commander, items: selected media]
    #   戻り値: [selection result]
    # }
    def select(self, items):
        return self._target.select(items)

    # {
    #   責務: [options: current available Inspector actionsをUIへ返す]
    #   処理: [target.options resultをそのまま返す]
    #   引数: [self: commander]
    #   戻り値: [ActionAvailability sequence]
    # }
    def options(self):
        return self._target.options()

    # {
    #   責務: [notes: currently selected media item notesを取得する]
    #   処理: [target.notesを呼ぶ]
    #   引数: [self: commander]
    #   戻り値: [MediaNotesまたはNone]
    # }
    def notes(self):
        return self._target.notes()

    # {
    #   責務: [save_notes: UI編集済みMediaNotesをsession cacheへ保存依頼する]
    #   処理: [target.save_notesへnotesを転送する]
    #   引数: [self: commander, notes: edited MediaNotes]
    #   戻り値: [save result]
    # }
    def save_notes(self, notes):
        return self._target.save_notes(notes)

    # {
    #   責務: [status: current busy/ready/model stateをUIへ返す]
    #   処理: [target.statusへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [InspectorStatus]
    # }
    def status(self):
        return self._target.status()

    # {
    #   責務: [start: probe/tag kindでInspector actionを開始する]
    #   処理: [target.startへkindを渡す]
    #   引数: [self: commander, kind: Inspector action ID]
    #   戻り値: [start result]
    #   副作用: [background Data actionを開始する]
    # }
    def start(self, kind):
        return self._target.start(kind)

    # {
    #   責務: [export: 選択したanalysis notesのsidecar exportを依頼する]
    #   処理: [target.exportへExportSettingsを渡す]
    #   引数: [self: commander, settings: export destinations/options]
    #   戻り値: [export start result]
    # }
    def export(self, settings):
        return self._target.export(settings)

    # {
    #   責務: [poll: worker event pollを実行しstatus/messagesを更新する]
    #   処理: [target.poll resultを返す]
    #   引数: [self: commander]
    #   戻り値: [poll/update result]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [cancel: current Inspector workerへ停止要求を送る]
    #   処理: [target.cancelへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [cancel result]
    # }
    def cancel(self):
        return self._target.cancel()

    # {
    #   責務: [close: Inspector UI resource chainを閉じる]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [close result]
    #   副作用: [underlying action workerを終了する]
    # }
    def close(self):
        return self._target.close()
