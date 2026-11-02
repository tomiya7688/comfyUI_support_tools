"""Transport media IO requests/results without interpreting their contents."""

from comfyui_support_tools.applications.main_gui.data.messenger.media_messenger import (
    MediaDataMessenger,
)


# {
# 責務: [MediaDataRequests: process media commanderとData layer間のscan/preview requestsを運ぶ]
# フィールド: [_target: MediaDataMessenger]
# }
class MediaDataRequests:
    # {
    #   責務: [__init__: MediaDataMessenger targetを保持する]
    #   処理: [全scan/preview/poll/close requestを同じdelegateへ接続する]
    #   引数: [self: request boundary, target: MediaDataMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: MediaDataMessenger):
        self._target = target

    # {
    #   責務: [scan: folder/collection requestをData layerへ送る]
    #   処理: [target.scanのresult/errorを転送する]
    #   引数: [self: request boundary, folder: media root, collection: collection label]
    #   戻り値: [scan generation token]
    #   副作用: [background scanを開始する]
    # }
    def scan(self, folder, collection):
        return self._target.scan(folder, collection)

    # {
    #   責務: [thumbnails: token付きitem batchのthumbnail requestをDataへ送る]
    #   処理: [items/tokenを加工せずtargetへ渡す]
    #   引数: [self: request boundary, token: view generation, items: MediaItem sequence]
    #   戻り値: [request result]
    # }
    def thumbnails(self, token, items):
        return self._target.thumbnails(token, items)

    # {
    #   責務: [preview: token/item/fraction付きpreview requestをDataへ送る]
    #   処理: [target.previewへ引数を転送する]
    #   引数: [self: request boundary, token: view generation, item: MediaItem, fraction: seek position]
    #   戻り値: [request result]
    # }
    def preview(self, token, item, fraction):
        return self._target.preview(token, item, fraction)

    # {
    #   責務: [poll: completed scan/preview eventをData layerから取得する]
    #   処理: [target.pollを呼ぶ]
    #   引数: [self: request boundary]
    #   戻り値: [MediaEvent sequence]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [close: media data workerをshutdownするrequestを伝える]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: request boundary]
    #   戻り値: [close result]
    #   副作用: [background worker terminationを依頼する]
    # }
    def close(self):
        return self._target.close()
