"""Transport Inspector messages without interpreting their contents."""

from comfyui_support_tools.applications.main_gui.process.commander.inspector_commander import (
    InspectorCommander,
)


# {
# 責務: [InspectorProcessMessenger: InspectorCommander操作をUI messenger向けに転送する]
# フィールド: [_target: InspectorCommander]
# }
class InspectorProcessMessenger:
    # {
    #   責務: [__init__: InspectorCommander delegateを保持する]
    #   処理: [targetを全Inspector message handlerへ接続する]
    #   引数: [self: messenger, target: InspectorCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, target: InspectorCommander):
        self._target = target

    # {
    #   責務: [configure: TaggerSettings更新messageをProcess commanderへ転送する]
    #   処理: [target.configureへsettingsを渡す]
    #   引数: [self: messenger, settings: TaggerSettings]
    #   戻り値: [configuration result]
    # }
    def configure(self, settings):
        return self._target.configure(settings)

    # {
    #   責務: [select: selected MediaItem sequenceをInspectorへ転送する]
    #   処理: [target.selectへitemsを渡す]
    #   引数: [self: messenger, items: selected MediaItems]
    #   戻り値: [selection result]
    # }
    def select(self, items):
        return self._target.select(items)

    # {
    #   責務: [options: current action availabilityをcommanderから取得する]
    #   処理: [target.optionsを呼ぶ]
    #   引数: [self: messenger]
    #   戻り値: [ActionAvailability sequence]
    # }
    def options(self):
        return self._target.options()

    # {
    #   責務: [notes: current selected media notesをcommanderから取得する]
    #   処理: [target.notesへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [MediaNotes]
    # }
    def notes(self):
        return self._target.notes()

    # {
    #   責務: [save_notes: changed MediaNotesをselected itemへ保存依頼する]
    #   処理: [target.save_notesへnotesを渡す]
    #   引数: [self: messenger, notes: updated MediaNotes]
    #   戻り値: [save result]
    # }
    def save_notes(self, notes):
        return self._target.save_notes(notes)

    # {
    #   責務: [status: current InspectorStatusを取得する]
    #   処理: [target.statusを返す]
    #   引数: [self: messenger]
    #   戻り値: [InspectorStatus]
    # }
    def status(self):
        return self._target.status()

    # {
    #   責務: [start: kind付きprobe/tag actionをProcess commander経由で開始する]
    #   処理: [target.startへkindを渡す]
    #   引数: [self: messenger, kind: action kind]
    #   戻り値: [start result]
    #   副作用: [Data layer worker requestを開始する]
    # }
    def start(self, kind):
        return self._target.start(kind)

    # {
    #   責務: [export: ExportSettingsで選択したmedia analysisを出力依頼する]
    #   処理: [target.exportへsettingsを渡す]
    #   引数: [self: messenger, settings: ExportSettings]
    #   戻り値: [export start result]
    # }
    def export(self, settings):
        return self._target.export(settings)

    # {
    #   責務: [poll: pending Data action eventsをProcess stateへ反映する]
    #   処理: [target.pollへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [Inspector state update result]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [cancel: current Inspector operationのcancelを要求する]
    #   処理: [target.cancelへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [cancel result]
    # }
    def cancel(self):
        return self._target.cancel()

    # {
    #   責務: [close: Inspector Process/Data resource chainを閉じる]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [underlying action worker resourceを終了する]
    # }
    def close(self):
        return self._target.close()
