"""Carry Job state between Process and Data layers."""

from comfyui_support_tools.applications.main_gui.data.messenger.job_messenger import (
    JobDataMessenger,
)


# {
# 責務: [JobDataRequests: Process commander向けjob data requestをJobDataMessengerへ転送する]
# フィールド: [_target: JobDataMessenger]
# }
class JobDataRequests:
    # {
    #   責務: [__init__: JobDataMessenger targetを保持する]
    #   処理: [targetを各job requestのdelegateに設定する]
    #   引数: [self: request boundary, target: JobDataMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: JobDataMessenger):
        self._target = target

    # {
    #   責務: [snapshots: Data layerからcurrent job history snapshotを取得する]
    #   処理: [target.snapshotsへ委譲する]
    #   引数: [self: request boundary]
    #   戻り値: [JobSnapshot sequence]
    # }
    def snapshots(self):
        return self._target.snapshots()

    # {
    #   責務: [cancel: local job IDをData layerへ渡してcancelを要求する]
    #   処理: [target.cancel result/errorを転送する]
    #   引数: [self: request boundary, job_id: local job ID]
    #   戻り値: [cancel result]
    # }
    def cancel(self, job_id):
        return self._target.cancel(job_id)

    # {
    #   責務: [set_backend_job_id: remote backend identifierをjob stateへ記録するrequestを送る]
    #   処理: [両identifierをtarget.set_backend_job_idへ渡す]
    #   引数: [self: request boundary, job_id: local job ID, backend_job_id: remote ID]
    #   戻り値: [update result]
    # }
    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    # {
    #   責務: [close: Data job resource chainを閉じるrequestを送る]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: request boundary]
    #   戻り値: [close result]
    #   副作用: [runtime shutdownを伝える]
    # }
    def close(self):
        return self._target.close()
