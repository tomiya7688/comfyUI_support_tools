"""Route local-media IO to its worker implementation."""

from comfyui_support_tools.applications.main_gui.data.processing.media_io import MediaIO


# {
# 責務: [MediaDataCommander: MediaIOのscan/thumbnail/preview/poll/closeをData boundaryへ公開する]
# フィールド: [_io: local media worker adapter]
# }
class MediaDataCommander:
    # {
    #   責務: [__init__: MediaIO implementationを保持する]
    #   処理: [渡されたioを全media operationのdelegateにする]
    #   引数: [self: commander, io: MediaIO worker adapter]
    #   戻り値: [なし]
    # }
    def __init__(self, io: MediaIO):
        self._io = io

    # {
    #   責務: [scan: folder/collectionをMediaIO scan workerへ渡す]
    #   処理: [同じfolderとcollectionでio.scanを呼ぶ]
    #   引数: [self: commander, folder: scan root, collection: collection label]
    #   戻り値: [io.scan result]
    #   副作用: [background media scanを依頼する]
    # }
    def scan(self, folder, collection):
        return self._io.scan(folder, collection)

    # {
    #   責務: [thumbnails: tokenとmedia item batchのthumbnail生成を依頼する]
    #   処理: [引数をそのままio.thumbnailsへ渡す]
    #   引数: [self: commander, token: request generation token, items: 対象MediaItem sequence]
    #   戻り値: [io.thumbnails result]
    #   副作用: [thumbnail worker requestをenqueueする]
    # }
    def thumbnails(self, token, items):
        return self._io.thumbnails(token, items)

    # {
    #   責務: [preview: token付きmedia item preview requestをMediaIOへ送る]
    #   処理: [itemとfractionを変更せずio.previewへ委譲する]
    #   引数: [self: commander, token: request generation, item: MediaItem, fraction: video seek fraction]
    #   戻り値: [io.preview result]
    #   副作用: [preview decodeを依頼する]
    # }
    def preview(self, token, item, fraction):
        return self._io.preview(token, item, fraction)

    # {
    #   責務: [poll: MediaIOから非同期scan/thumbnail/preview resultを回収する]
    #   処理: [io.poll resultをそのまま返す]
    #   引数: [self: commander]
    #   戻り値: [pending MediaEvent sequence]
    # }
    def poll(self):
        return self._io.poll()

    # {
    #   責務: [close: MediaIO workerを終了する]
    #   処理: [io.closeへ委譲する]
    #   引数: [self: commander]
    #   戻り値: [なし]
    #   副作用: [media worker resourceを閉じる]
    # }
    def close(self):
        self._io.close()
