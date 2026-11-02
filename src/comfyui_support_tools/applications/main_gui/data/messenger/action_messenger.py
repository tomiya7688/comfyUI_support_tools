"""Forward Action IO through the explicit UPD boundary."""

from comfyui_support_tools.applications.main_gui.data.commander.action_commander import (
    ActionDataCommander,
)


# {
# 責務: [ActionDataMessenger: ActionDataCommanderのrequest/resultをdata messenger boundaryに転送する]
# フィールド: [_target: ActionDataCommander delegate]
# }
class ActionDataMessenger:
    # {
    #   責務: [__init__: ActionDataCommander delegateを保持する]
    #   処理: [同じtargetを各operationへ渡す]
    #   引数: [self: messenger, target: ActionDataCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, target: ActionDataCommander):
        self._target = target

    # {
    #   責務: [start: action requestをcommanderへ転送する]
    #   処理: [target.startのresult/errorを変換せず返す]
    #   引数: [self: messenger, request: action request]
    #   戻り値: [target.start result]
    # }
    def start(self, request):
        return self._target.start(request)

    # {
    #   責務: [poll: commanderからpending action eventを取得する]
    #   処理: [target.pollへ委譲する]
    #   引数: [self: messenger]
    #   戻り値: [pending ActionEvent sequence]
    # }
    def poll(self):
        return self._target.poll()

    # {
    #   責務: [cancel: commander経由でactive actionのcancelを要求する]
    #   処理: [target.cancelのresult/errorを転送する]
    #   引数: [self: messenger]
    #   戻り値: [target.cancel result]
    # }
    def cancel(self):
        return self._target.cancel()

    # {
    #   責務: [close: underlying ActionIO resourceをcommander経由で閉じる]
    #   処理: [target.closeへ委譲する]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [underlying workerを終了させる]
    # }
    def close(self):
        return self._target.close()
