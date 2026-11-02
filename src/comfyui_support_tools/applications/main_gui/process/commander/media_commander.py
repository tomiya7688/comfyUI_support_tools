"""Coordinate query state and asynchronous Data requests; no filesystem/Tk work."""

from comfyui_support_tools.applications.main_gui.process.messenger.media_data_messenger import (
    MediaDataRequests,
)
from comfyui_support_tools.applications.main_gui.process.processing.media_session import (
    MediaSession,
)


# {
# 責務: [MediaCommander: MediaSession query/selection stateとasync MediaDataRequestsを調整する]
# フィールド: [_state: media browser session, _data: scan/preview data boundary]
# }
class MediaCommander:
    # {
    #   責務: [__init__: media session stateとdata request boundaryを接続する]
    #   処理: [state/data referencesをoperation delegateとして保存する]
    #   引数: [self: commander, state: MediaSession, data: MediaDataRequests]
    #   戻り値: [なし]
    # }
    def __init__(self, state: MediaSession, data: MediaDataRequests):
        self._state = state
        self._data = data

    # {
    #   責務: [load: folder scanをDataへ依頼し返却tokenでsession generationを開始する]
    #   処理: [data.scanのtokenをstate.beginへ渡す]
    #   引数: [self: commander, folder: scan root, collection: collection label]
    #   戻り値: [なし]
    #   副作用: [async scan requestを開始しsession resultsをresetする]
    # }
    def load(self, folder, collection):
        token = self._data.scan(folder, collection)
        self._state.begin(token)

    # {
    #   責務: [poll: Data eventsを回収しsessionへ適用して変化有無とeventsを返す]
    #   処理: [data.poll後にstate.acceptを呼ぶ]
    #   引数: [self: commander]
    #   戻り値: [(changed: bool, events: MediaEvent tuple)]
    # }
    def poll(self):
        events = self._data.poll()
        changed = self._state.accept(events)
        return changed, events

    # {
    #   責務: [view: current page itemsとmedia browser summaryを組で返す]
    #   処理: [page_itemsとsummaryをstateから取得する]
    #   引数: [self: commander]
    #   戻り値: [(current MediaItem page, summary mapping)]
    # }
    def view(self):
        items = self._state.page_items()
        return items, self._state.summary()

    # {
    #   責務: [query: section/text/sort変更をsession stateへ適用する]
    #   処理: [state.queryへfilter/sort parametersを渡す]
    #   引数: [self: commander, section: active section, text: search text, sort: field, descending: order]
    #   戻り値: [なし]
    # }
    def query(self, section, text, sort, descending):
        self._state.query(section, text, sort, descending)

    # {
    #   責務: [move_page: page indexをdelta分session内で移動する]
    #   処理: [state.move_pageへdeltaを渡す]
    #   引数: [self: commander, delta: relative page offset]
    #   戻り値: [なし]
    # }
    def move_page(self, delta):
        self._state.move_page(delta)

    # {
    #   責務: [select: item keysをsession selectionへ適用する]
    #   処理: [state.select resultを返す]
    #   引数: [self: commander, keys: selected item IDs]
    #   戻り値: [selection update result]
    # }
    def select(self, keys):
        return self._state.select(keys)

    # {
    #   責務: [selection: current selected MediaItem sequenceを取得する]
    #   処理: [state.selectionを返す]
    #   引数: [self: commander]
    #   戻り値: [selected MediaItem tuple]
    # }
    def selection(self):
        return self._state.selection()

    # {
    #   責務: [toggle_favorites: current selected item IDsのfavorite stateを切り替える]
    #   処理: [state.toggle_favoritesへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [なし]
    # }
    def toggle_favorites(self):
        self._state.toggle_favorites()

    # {
    #   責務: [thumbnails: current page item thumbnailsを有効時にDataへ要求する]
    #   処理: [enabled falseなら空batch、trueならstate.page_itemsを渡す]
    #   引数: [self: commander, token: view generation, enabled: thumbnail fetchを有効にするか]
    #   戻り値: [data thumbnail request result]
    # }
    def thumbnails(self, token, enabled=True):
        return self._data.thumbnails(token, self._state.page_items() if enabled else ())

    # {
    #   責務: [preview: selection先頭itemのpreviewをfraction位置で要求する]
    #   処理: [selectionがある場合に限りdata.previewへitemを渡す]
    #   引数: [self: commander, token: view generation, fraction: seek fraction]
    #   戻り値: [preview request resultまたはNone]
    # }
    def preview(self, token, fraction):
        selection = self._state.selection()
        if selection:
            self._data.preview(token, selection[0], fraction)

    # {
    #   責務: [close: media Data worker boundaryを終了する]
    #   処理: [data.closeを呼ぶ]
    #   引数: [self: commander]
    #   戻り値: [close result]
    #   副作用: [scan/preview workerを停止する]
    # }
    def close(self):
        self._data.close()
