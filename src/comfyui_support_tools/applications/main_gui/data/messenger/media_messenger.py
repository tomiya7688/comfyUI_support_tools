"""Transport media IO requests/results without interpreting their contents."""

from comfyui_support_tools.applications.main_gui.data.commander.media_commander import (
    MediaDataCommander,
)


# {
# 責務: [MediaDataMessenger: MediaDataCommanderのscan/preview/poll requestをdata messenger boundaryへ転送する]
# フィールド: [_target: MediaDataCommander delegate]
# }
class MediaDataMessenger:
    # {
    #   責務: [__init__: MediaDataCommander delegateを保持する]
    #   処理: [全media operationのtargetとして保存する]
    #   引数: [self: messenger, target: MediaDataCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, target: MediaDataCommander):
        self._target = target

    # {
    #   責務: [scan: folder/collection指定をmedia commanderへ転送する]
    #   処理: [同じfolderとcollectionでtarget.scanを呼ぶ]
    #   引数: [self: messenger, folder: scan root, collection: collection label]
    #   戻り値: [scan request result]
    # }
    def scan(self, folder, collection):
        return self._target.scan(folder, collection)

    # {
    #   責務: [thumbnails: request tokenとMediaItem batchをcommanderへ転送する]
    #   処理: [引数を加工せずtarget.thumbnailsへ渡す]
    #   引数: [self: messenger, token: generation token, items: MediaItem sequence]
    #   戻り値: [thumbnail request result]
    # }
    def thumbnails(self, token, items):
        return self._target.thumbnails(token, items)

    # {
    #   責務: [preview: request token/item/fractionをcommanderへ転送する]
    #   処理: [target.previewへ引数をそのまま渡す]
    #   引数: [self: messenger, token: generation token, item: MediaItem, fraction: seek fraction]
    #   戻り値: [preview request result]
    # }
    def preview(self, token, item, fraction):
        return self._target.preview(token, item, fraction)

    # {
    #   責務: [poll: pending MediaEventをcommanderから取得する]
    #   処理: [target.pollの結果をそのまま返す]
    #   引数: [self: messenger]
    #   戻り値: [pending MediaEvent sequence]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [close: media commander経由でworker resourceを閉じる]
    #   処理: [target.closeへ委譲する]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [media workerを終了させる]
    # }
    def close(self):
        return self._target.close()
