"""Transport Job UI requests to the Process Commander."""

from comfyui_support_tools.applications.main_gui.process.commander.job_queue_commander import (
    JobQueueCommander,
)


# {
# 責務: [JobProcessMessenger: UIとJobQueueCommander間のjob messagesを転送する]
# フィールド: [_target: JobQueueCommander]
# }
class JobProcessMessenger:
    # {
    #   責務: [__init__: JobQueueCommander delegateを保持する]
    #   処理: [targetをUI-originated job message handlerとして設定する]
    #   引数: [self: messenger, target: JobQueueCommander]
    #   戻り値: [なし]
    # }
    def __init__(self, target: JobQueueCommander):
        self._target = target

    # {
    #   責務: [snapshots: UI表示用job historyを取得する]
    #   処理: [target.snapshots resultを返す]
    #   引数: [self: messenger]
    #   戻り値: [JobSnapshot sequence]
    # }
    def snapshots(self):
        return self._target.snapshots()

    # {
    #   責務: [cancel: user選択jobのcancel requestをProcess commanderへ送る]
    #   処理: [target.cancelへjob_idを渡す]
    #   引数: [self: messenger, job_id: selected local job ID]
    #   戻り値: [cancel result]
    # }
    def cancel(self, job_id):
        return self._target.cancel(job_id)

    # {
    #   責務: [set_backend_job_id: backend operation identifierをshared jobへ登録する]
    #   処理: [target methodへlocal IDとbackend IDを転送する]
    #   引数: [self: messenger, job_id: local ID, backend_job_id: remote ID]
    #   戻り値: [update result]
    # }
    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    # {
    #   責務: [close: job queue UI messenger経由でruntime resourceを閉じる]
    #   処理: [target.closeへ委譲する]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [underlying job runtimeをcloseする]
    # }
    def close(self):
        return self._target.close()
