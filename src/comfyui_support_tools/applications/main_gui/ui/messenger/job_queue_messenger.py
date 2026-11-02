"""Transport Job UI requests across the UI/Process boundary."""

from comfyui_support_tools.applications.main_gui.process.messenger.job_queue_messenger import (
    JobProcessMessenger,
)


# {
# 責務: [JobUiMessenger: UI job panel callsをProcess JobProcessMessengerへ運ぶ]
# フィールド: [_target: JobProcessMessenger]
# }
class JobUiMessenger:
    # {
    #   責務: [__init__: JobProcessMessenger targetを保持する]
    #   処理: [queue messagesのdelegateとして保存する]
    #   引数: [self: messenger, target: JobProcessMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: JobProcessMessenger):
        self._target = target

    # {
    #   責務: [snapshots: UI job list用のcurrent snapshotsを取得する]
    #   処理: [target.snapshotsを呼ぶ]
    #   引数: [self: messenger]
    #   戻り値: [JobSnapshot sequence]
    # }
    def snapshots(self):
        return self._target.snapshots()

    # {
    #   責務: [cancel: UI job cancel commandをProcess layerへ渡す]
    #   処理: [target.cancelへjob_idを転送する]
    #   引数: [self: messenger, job_id: selected job identifier]
    #   戻り値: [cancel result]
    # }
    def cancel(self, job_id):
        return self._target.cancel(job_id)

    # {
    #   責務: [set_backend_job_id: backend ID updateをProcess layerへ転送する]
    #   処理: [target methodへlocal ID/backend IDを渡す]
    #   引数: [self: messenger, job_id: local ID, backend_job_id: remote ID]
    #   戻り値: [update result]
    # }
    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    # {
    #   責務: [close: UI job messenger経由でruntime shutdownを依頼する]
    #   処理: [target.closeへdelegateする]
    #   引数: [self: messenger]
    #   戻り値: [close result]
    #   副作用: [runtime resourceを終了する]
    # }
    def close(self):
        return self._target.close()
