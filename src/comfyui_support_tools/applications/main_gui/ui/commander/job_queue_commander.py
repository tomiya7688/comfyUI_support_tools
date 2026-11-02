"""UI-facing Job Queue contract."""

from comfyui_support_tools.applications.main_gui.ui.messenger.job_queue_messenger import (
    JobUiMessenger,
)


# {
# 責務: [JobQueueUiCommander: UI caller向けjob snapshots/cancel/close operationsを公開する]
# フィールド: [_target: JobUiMessenger]
# }
class JobQueueUiCommander:
    # {
    #   責務: [__init__: JobUiMessenger delegateを保持する]
    #   処理: [queue operationsを下位messengerへ接続する]
    #   引数: [self: commander, target: JobUiMessenger]
    #   戻り値: [なし]
    # }
    def __init__(self, target: JobUiMessenger):
        self._target = target

    # {
    #   責務: [snapshots: UI panelで描画する最新JobSnapshot一覧を返す]
    #   処理: [target.snapshotsへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [JobSnapshot sequence]
    # }
    def snapshots(self):
        return self._target.snapshots()

    # {
    #   責務: [cancel: UIから指定job IDのcancelを依頼する]
    #   処理: [target.cancelへjob IDを渡す]
    #   引数: [self: commander, job_id: selected job identifier]
    #   戻り値: [cancel result]
    # }
    def cancel(self, job_id):
        return self._target.cancel(job_id)

    # {
    #   責務: [set_backend_job_id: backend operation IDをUI経由でruntimeへ関連付ける]
    #   処理: [targetへlocal/backend IDsを渡す]
    #   引数: [self: commander, job_id: local job ID, backend_job_id: remote ID]
    #   戻り値: [update result]
    # }
    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    # {
    #   責務: [close: UI job queueが参照するruntime resource chainを閉じる]
    #   処理: [target.closeを呼ぶ]
    #   引数: [self: commander]
    #   戻り値: [close result]
    #   副作用: [runtime shutdownを要求する]
    # }
    def close(self):
        return self._target.close()
