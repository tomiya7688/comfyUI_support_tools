"""Forward media requests over the explicit UPD boundary."""

from comfyui_support_tools.applications.main_gui.process.messenger.media_messenger import (
    MediaProcessMessenger,
)


# {
# 責務: [MediaUiMessenger: browser UI requests/eventsをMediaProcessMessengerへ転送する]
# フィールド: [_target: MediaProcessMessenger]
# }
class MediaUiMessenger:
    # {
    #   責務: [__init__: MediaProcessMessenger delegateを保持する]
    #   処理: [UI media messagesの委譲先を設定する]
    #   引数: [self: messenger, target: MediaProcessMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: MediaProcessMessenger):
        self._target = target

    # {
    #   責務: [load: UIからfolder/collection scanを開始する]
    #   処理: [target.loadへpath/collectionを渡す]
    #   引数: [self: messenger, folder: scan root, collection: collection ID]
    #   戻り値: [load result]
    # }
    def load(self, folder, collection):
        return self._target.load(folder, collection)

    # {
    #   責務: [poll: MediaEventを受けてbrowser view stateを同期する]
    #   処理: [target.poll resultを返す]
    #   引数: [self: messenger]
    #   戻り値: [(changed, events)]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [view: UI render対象のMediaItem pageとsummaryを取得する]
    #   処理: [target.viewへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [(MediaItem tuple, summary mapping)]
    # }
    def view(self):
        return self._target.view()

    # {
    #   責務: [query: UI section/search/sort/order selectionをProcessへ伝える]
    #   処理: [query fieldsをtarget.queryへ転送する]
    #   引数: [self: messenger, section/text/sort/descending: active query values]
    #   戻り値: [なし]
    # }
    def query(self, section, text, sort, descending):
        return self._target.query(section, text, sort, descending)

    # {
    #   責務: [move_page: UI page navigation deltaをProcessへ送る]
    #   処理: [target.move_pageへdeltaを渡す]
    #   引数: [self: messenger, delta: relative page step]
    #   戻り値: [なし]
    # }
    def move_page(self, delta):
        return self._target.move_page(delta)

    # {
    #   責務: [select: UI selected row/item keysをsession stateへ伝える]
    #   処理: [target.selectへkeysを渡す]
    #   引数: [self: messenger, keys: media item IDs]
    #   戻り値: [selected MediaItem tuple]
    # }
    def select(self, keys):
        return self._target.select(keys)

    # {
    #   責務: [selection: current selected MediaItem tupleを取得する]
    #   処理: [target.selectionを返す]
    #   引数: [self: messenger]
    #   戻り値: [MediaItem tuple]
    # }
    def selection(self):
        return self._target.selection()

    # {
    #   責務: [toggle_favorites: current selected IDsをfavorite/unfavoriteする操作を渡す]
    #   処理: [target.toggle_favoritesへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [なし]
    # }
    def toggle_favorites(self):
        return self._target.toggle_favorites()

    # {
    #   責務: [thumbnails: current page thumbnailsのtoken/enabled設定をProcessへ渡す]
    #   処理: [target.thumbnailsを呼ぶ]
    #   引数: [self: messenger, token: generation, enabled: decode request flag]
    #   戻り値: [request result]
    # }
    def thumbnails(self, token, enabled=True):
        return self._target.thumbnails(token, enabled)

    # {
    #   責務: [preview: selected item preview requestとseek fractionをProcessへ送る]
    #   処理: [target.previewへ引数を渡す]
    #   引数: [self: messenger, token: generation, fraction: seek fraction]
    #   戻り値: [request result]
    # }
    def preview(self, token, fraction):
        return self._target.preview(token, fraction)

    # {
    #   責務: [close: UI media messenger経由でworker resourcesをshutdownする]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [media scan/preview workerの停止を通知する]
    # }
    def close(self):
        return self._target.close()
