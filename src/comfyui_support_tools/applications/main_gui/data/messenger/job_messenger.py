"""Transport Job model requests without backend-specific interpretation."""

from comfyui_support_tools.applications.main_gui.data.commander.job_commander import (
    JobDataCommander,
)


# {
# 責務: [JobDataMessenger: JobDataCommanderのsnapshot/cancel/backend ID/close requestを転送する]
# フィールド: [_target: JobDataCommander delegate]
# }
class JobDataMessenger:
    # {
    #   責務: [__init__: JobDataCommander delegateを保持する]
    #   処理: [全job operationの同じtargetとして保存する]
    #   引数: [self: messenger, target: JobDataCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, target: JobDataCommander):
        self._target = target

    # {
    #   責務: [snapshots: runtimeが保持するcurrent JobSnapshot一覧を取得する]
    #   処理: [target.snapshotsのresultをそのまま返す]
    #   引数: [self: messenger]
    #   戻り値: [JobSnapshot sequence]
    # }
    def snapshots(self):
        return self._target.snapshots()

    # {
    #   責務: [cancel: 指定job IDのcancelをcommanderへ転送する]
    #   処理: [job_idを変更せずtarget.cancelへ渡す]
    #   引数: [self: messenger, job_id: target job ID]
    #   戻り値: [cancel result]
    # }
    def cancel(self, job_id):
        return self._target.cancel(job_id)

    # {
    #   責務: [set_backend_job_id: local job IDとbackend IDの関連付けをcommanderへ転送する]
    #   処理: [両IDをそのままtargetへ渡す]
    #   引数: [self: messenger, job_id: local ID, backend_job_id: backend ID]
    #   戻り値: [runtime update result]
    # }
    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    # {
    #   責務: [close: job runtime lifecycleをcommander経由で終了する]
    #   処理: [target.closeを呼ぶ]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [runtime worker resourceを閉じる]
    # }
    def close(self):
        return self._target.close()
