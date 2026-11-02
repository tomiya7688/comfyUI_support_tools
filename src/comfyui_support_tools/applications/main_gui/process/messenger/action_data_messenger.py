"""Forward Action IO through the explicit UPD boundary."""

from comfyui_support_tools.applications.main_gui.data.messenger.action_messenger import (
    ActionDataMessenger,
)


# {
# 責務: [ActionDataRequests: ActionDataMessengerへのstart/poll/cancel/close requestをProcessから送る]
# フィールド: [_target: data-layer ActionDataMessenger]
# }
class ActionDataRequests:
    # {
    #   責務: [__init__: ActionDataMessenger delegateを保持する]
    #   処理: [target referenceを全request operationへ共有する]
    #   引数: [self: request boundary, target: ActionDataMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: ActionDataMessenger):
        self._target = target

    # {
    #   責務: [start: ActionRequestをData layerへ転送する]
    #   処理: [target.start result/errorをそのまま返す]
    #   引数: [self: request boundary, request: ActionRequest]
    #   戻り値: [target.start result]
    #   副作用: [Data workerへrequestを送信する]
    # }
    def start(self, request):
        return self._target.start(request)

    # {
    #   責務: [poll: Data layerからpending ActionEventを回収する]
    #   処理: [target.pollを呼ぶ]
    #   引数: [self: request boundary]
    #   戻り値: [ActionEvent sequence]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [cancel: active Data actionへcancelを転送する]
    #   処理: [target.cancelへ委譲する]
    #   引数: [self: request boundary]
    #   戻り値: [cancel result]
    # }
    def cancel(self):
        return self._target.cancel()

    # {
    #   責務: [close: Action Data boundaryを閉じる]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: request boundary]
    #   戻り値: [close result]
    #   副作用: [underlying worker shutdownを伝える]
    # }
    def close(self):
        return self._target.close()
