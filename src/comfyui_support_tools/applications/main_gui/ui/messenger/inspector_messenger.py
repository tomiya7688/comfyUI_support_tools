"""Transport Inspector messages without interpreting their contents."""

from comfyui_support_tools.applications.main_gui.process.messenger.inspector_messenger import (
    InspectorProcessMessenger,
)


# {
# 責務: [InspectorUiMessenger: UI-originated Inspector callsをProcess messenger boundaryへ運ぶ]
# フィールド: [_target: InspectorProcessMessenger]
# }
class InspectorUiMessenger:
    # {
    #   責務: [__init__: InspectorProcessMessenger delegateを保持する]
    #   処理: [UI requestのtargetを保存する]
    #   引数: [self: messenger, target: InspectorProcessMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: InspectorProcessMessenger):
        self._target = target

    # {
    #   責務: [configure: Tagger settings変更をProcessへ転送する]
    #   処理: [target.configureへsettingsを渡す]
    #   引数: [self: messenger, settings: TaggerSettings]
    #   戻り値: [configuration result]
    # }
    def configure(self, settings):
        return self._target.configure(settings)

    # {
    #   責務: [select: current UI media selectionをInspector processへ渡す]
    #   処理: [target.selectへitemsを転送する]
    #   引数: [self: messenger, items: MediaItem selection]
    #   戻り値: [selection result]
    # }
    def select(self, items):
        return self._target.select(items)

    # {
    #   責務: [options: UI用Inspector action availabilityを取得する]
    #   処理: [target.optionsを返す]
    #   引数: [self: messenger]
    #   戻り値: [ActionAvailability sequence]
    # }
    def options(self):
        return self._target.options()

    # {
    #   責務: [notes: current selected item notesをProcessから取得する]
    #   処理: [target.notesへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [MediaNotesまたはNone]
    # }
    def notes(self):
        return self._target.notes()

    # {
    #   責務: [save_notes: UI編集済みnotesをProcess sessionへ送る]
    #   処理: [target.save_notesへnotesを渡す]
    #   引数: [self: messenger, notes: edited MediaNotes]
    #   戻り値: [save result]
    # }
    def save_notes(self, notes):
        return self._target.save_notes(notes)

    # {
    #   責務: [status: current InspectorStatus snapshotを取得する]
    #   処理: [target.statusを呼ぶ]
    #   引数: [self: messenger]
    #   戻り値: [InspectorStatus]
    # }
    def status(self):
        return self._target.status()

    # {
    #   責務: [start: userが選んだ action kindでInspector operationを開始する]
    #   処理: [target.startへkindを渡す]
    #   引数: [self: messenger, kind: action identifier]
    #   戻り値: [start result]
    # }
    def start(self, kind):
        return self._target.start(kind)

    # {
    #   責務: [export: userのExportSettingsでsidecar outputを開始する]
    #   処理: [target.exportへsettingsを転送する]
    #   引数: [self: messenger, settings: ExportSettings]
    #   戻り値: [export result]
    # }
    def export(self, settings):
        return self._target.export(settings)

    # {
    #   責務: [poll: Inspector worker eventsをProcess stateへ反映する]
    #   処理: [target.poll resultを返す]
    #   引数: [self: messenger]
    #   戻り値: [poll result/messages]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [cancel: current Inspector actionへcancellation requestを送る]
    #   処理: [target.cancelへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [cancel result]
    # }
    def cancel(self):
        return self._target.cancel()

    # {
    #   責務: [close: Inspector operation chainのcloseをProcessへ伝える]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [underlying worker shutdownを開始する]
    # }
    def close(self):
        return self._target.close()
