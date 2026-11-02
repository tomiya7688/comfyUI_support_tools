"""Forward media requests over the explicit UPD boundary."""

from comfyui_support_tools.applications.main_gui.process.commander.media_commander import (
    MediaCommander,
)


# {
# 責務: [MediaProcessMessenger: UI-facing media messagesをMediaCommanderへ転送する]
# フィールド: [_target: MediaCommander]
# }
class MediaProcessMessenger:
    # {
    #   責務: [__init__: MediaCommander delegateを保持する]
    #   処理: [各media UI message handlerを同じProcess commanderに結び付ける]
    #   引数: [self: messenger, target: MediaCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, target: MediaCommander):
        self._target = target

    # {
    #   責務: [load: folder/collection scan actionをcommanderへ転送する]
    #   処理: [target.loadへ入力を渡す]
    #   引数: [self: messenger, folder: scan root, collection: media collection]
    #   戻り値: [load result]
    # }
    def load(self, folder, collection):
        return self._target.load(folder, collection)

    # {
    #   責務: [poll: async media eventsをsessionへ反映したpoll resultを取得する]
    #   処理: [target.pollへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [(changed, MediaEvent sequence)]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [view: current page itemsとsummaryを取得する]
    #   処理: [target.viewを呼ぶ]
    #   引数: [self: messenger]
    #   戻り値: [(MediaItem page, summary mapping)]
    # }
    def view(self):
        return self._target.view()

    # {
    #   責務: [query: section/search/sort UI stateをsessionへ伝える]
    #   処理: [target.queryへ4つのquery fieldを渡す]
    #   引数: [self: messenger, section: section key, text: search text, sort: sort field, descending: order flag]
    #   戻り値: [なし]
    # }
    def query(self, section, text, sort, descending):
        return self._target.query(section, text, sort, descending)

    # {
    #   責務: [move_page: UIのrelative page navigation requestを転送する]
    #   処理: [target.move_pageへdeltaを渡す]
    #   引数: [self: messenger, delta: page offset]
    #   戻り値: [なし]
    # }
    def move_page(self, delta):
        return self._target.move_page(delta)

    # {
    #   責務: [select: selected media IDsをsessionへ適用する]
    #   処理: [target.select resultを返す]
    #   引数: [self: messenger, keys: selected item IDs]
    #   戻り値: [selection result]
    # }
    def select(self, keys):
        return self._target.select(keys)

    # {
    #   責務: [selection: current selected MediaItemsを取得する]
    #   処理: [target.selectionへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [MediaItem sequence]
    # }
    def selection(self):
        return self._target.selection()

    # {
    #   責務: [toggle_favorites: selected media itemsのfavorite state変更を依頼する]
    #   処理: [target.toggle_favoritesを呼ぶ]
    #   引数: [self: messenger]
    #   戻り値: [なし]
    # }
    def toggle_favorites(self):
        return self._target.toggle_favorites()

    # {
    #   責務: [thumbnails: current page thumbnail requestとenabled stateを転送する]
    #   処理: [target.thumbnailsにtoken/enabledを渡す]
    #   引数: [self: messenger, token: view generation, enabled: requestを有効化するか]
    #   戻り値: [request result]
    # }
    def thumbnails(self, token, enabled=True):
        return self._target.thumbnails(token, enabled)

    # {
    #   責務: [preview: selected item preview requestをfraction指定で転送する]
    #   処理: [target.previewへtoken/fractionを渡す]
    #   引数: [self: messenger, token: view generation, fraction: video seek fraction]
    #   戻り値: [preview request result]
    # }
    def preview(self, token, fraction):
        return self._target.preview(token, fraction)

    # {
    #   責務: [close: media browser Process/Data resource chainをcloseする]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [background media worker shutdownを依頼する]
    # }
    def close(self):
        return self._target.close()
