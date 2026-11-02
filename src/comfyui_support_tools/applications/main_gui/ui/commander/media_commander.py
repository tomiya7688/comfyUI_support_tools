"""Forward media requests over the explicit UPD boundary."""

from comfyui_support_tools.applications.main_gui.ui.messenger.media_messenger import (
    MediaUiMessenger,
)


# {
# 責務: [MediaUiCommander: UI向けmedia browser command surfaceをMediaUiMessengerへ接続する]
# フィールド: [_target: MediaUiMessenger]
# }
class MediaUiCommander:
    # {
    #   責務: [__init__: MediaUiMessenger delegateを保持する]
    #   処理: [UI media operationを下位messengerへ委譲する]
    #   引数: [self: commander, target: MediaUiMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: MediaUiMessenger):
        self._target = target

    # {
    #   責務: [load: directory/collection scanをUIから開始する]
    #   処理: [target.loadへ入力を渡す]
    #   引数: [self: commander, folder: root path, collection: collection key]
    #   戻り値: [load result]
    # }
    def load(self, folder, collection):
        return self._target.load(folder, collection)

    # {
    #   責務: [poll: scan/preview eventsを取得してview state update tupleを返す]
    #   処理: [target.pollへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [(changed, events)]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [view: current visible MediaItem pageとsummaryを返す]
    #   処理: [target.viewを呼ぶ]
    #   引数: [self: commander]
    #   戻り値: [(MediaItem tuple, summary mapping)]
    # }
    def view(self):
        return self._target.view()

    # {
    #   責務: [query: UI filter/sort settingsをbrowser stateへ適用する]
    #   処理: [target.queryへsection/text/sort/orderを転送する]
    #   引数: [self: commander, section/text/sort/descending: query fields]
    #   戻り値: [なし]
    # }
    def query(self, section, text, sort, descending):
        return self._target.query(section, text, sort, descending)

    # {
    #   責務: [move_page: UIからrelative media page移動を依頼する]
    #   処理: [target.move_pageへdeltaを渡す]
    #   引数: [self: commander, delta: page offset]
    #   戻り値: [なし]
    # }
    def move_page(self, delta):
        return self._target.move_page(delta)

    # {
    #   責務: [select: UI selected item IDsをsession stateへ適用する]
    #   処理: [target.select resultを返す]
    #   引数: [self: commander, keys: selected IDs]
    #   戻り値: [selected MediaItem tuple]
    # }
    def select(self, keys):
        return self._target.select(keys)

    # {
    #   責務: [selection: current selected media itemsを取得する]
    #   処理: [target.selectionを返す]
    #   引数: [self: commander]
    #   戻り値: [MediaItem tuple]
    # }
    def selection(self):
        return self._target.selection()

    # {
    #   責務: [toggle_favorites: current media selectionのfavorite stateを変更する]
    #   処理: [target.toggle_favoritesへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [なし]
    # }
    def toggle_favorites(self):
        return self._target.toggle_favorites()

    # {
    #   責務: [thumbnails: token付きcurrent-page thumbnail loadingを有効/無効にする]
    #   処理: [target.thumbnailsへtoken/enabledを渡す]
    #   引数: [self: commander, token: view generation, enabled: enable flag]
    #   戻り値: [request result]
    # }
    def thumbnails(self, token, enabled=True):
        return self._target.thumbnails(token, enabled)

    # {
    #   責務: [preview: selected media item previewをseek fraction指定で要求する]
    #   処理: [target.previewへtoken/fractionを渡す]
    #   引数: [self: commander, token: view generation, fraction: video seek fraction]
    #   戻り値: [request result]
    # }
    def preview(self, token, fraction):
        return self._target.preview(token, fraction)

    # {
    #   責務: [close: UI media browserを支えるworker resource chainを終了する]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [close result]
    #   副作用: [scan/preview workersをshutdownする]
    # }
    def close(self):
        return self._target.close()
