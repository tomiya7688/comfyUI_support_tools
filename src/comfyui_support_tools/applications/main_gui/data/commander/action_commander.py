"""Forward Action IO through the explicit UPD boundary."""

from comfyui_support_tools.applications.main_gui.data.processing.action_io import ActionIO


# {
# 責務: [ActionDataCommander: ActionIOのstart/poll/cancel/close操作をData境界に公開する]
# フィールド: [_target: ActionIO worker adapter]
# }
class ActionDataCommander:
    # {
    #   責務: [__init__: ActionIO targetを保存する]
    #   処理: [引数targetを_data boundaryのdelegateとして保持する]
    #   引数: [self: commander, target: ActionIO implementation]
    #   戻り値: [なし]
    # }
    def __init__(self, target: ActionIO):
        self._target = target

    # {
    #   責務: [start: action requestをActionIO workerへ開始依頼する]
    #   処理: [requestを変更せずtarget.startへ委譲する]
    #   引数: [self: commander, request: action request contract]
    #   戻り値: [target.start result]
    #   副作用: [ActionIO workerへrequestを送る]
    # }
    def start(self, request):
        return self._target.start(request)

    # {
    #   責務: [poll: ActionIOから完了済みaction eventを取得する]
    #   処理: [target.pollの結果をそのまま返す]
    #   引数: [self: commander]
    #   戻り値: [pending ActionEvent list]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [cancel: 実行中actionのcancelをActionIOへ依頼する]
    #   処理: [target.cancelを呼び戻り値を返す]
    #   引数: [self: commander]
    #   戻り値: [cancel request result]
    # }
    def cancel(self):
        return self._target.cancel()

    # {
    #   責務: [close: ActionIO worker resourceを閉じる]
    #   処理: [target.closeへ委譲する]
    #   引数: [self: commander]
    #   戻り値: [close result]
    #   副作用: [underlying workerを終了する]
    # }
    def close(self):
        return self._target.close()
