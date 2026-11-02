"""Coordinate Job list commands; execution remains inside Data adapters."""

from comfyui_support_tools.applications.main_gui.process.messenger.job_data_messenger import (
    JobDataRequests,
)


# {
# 責務: [JobQueueCommander: Data request境界経由でjob snapshot/cancel/backend ID/close操作を調整する]
# フィールド: [_data: JobDataRequests boundary]
# }
class JobQueueCommander:
    # {
    #   責務: [__init__: Data request boundaryを保持する]
    #   処理: [target data request objectをdelegateとして保存する]
    #   引数: [self: commander, data: JobDataRequests]
    #   戻り値: [なし]
    # }
    def __init__(self, data: JobDataRequests):
        self._data = data

    # {
    #   責務: [snapshots: current job historyをData request層から取得する]
    #   処理: [data.snapshotsへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [JobSnapshot sequence]
    # }
    def snapshots(self):
        return self._data.snapshots()

    # {
    #   責務: [cancel: 指定job IDのcancellationをData層へ依頼する]
    #   処理: [data.cancelへjob_idを渡す]
    #   引数: [self: commander, job_id: target job identifier]
    #   戻り値: [cancel result]
    # }
    def cancel(self, job_id):
        return self._data.cancel(job_id)

    # {
    #   責務: [set_backend_job_id: remote backend job IDをlocal jobへ関連付ける]
    #   処理: [両IDをdata request層へ渡す]
    #   引数: [self: commander, job_id: local ID, backend_job_id: backend ID]
    #   戻り値: [runtime update result]
    # }
    def set_backend_job_id(self, job_id, backend_job_id):
        return self._data.set_backend_job_id(job_id, backend_job_id)

    # {
    #   責務: [close: job data/runtime worker境界をcloseする]
    #   処理: [data.closeへdelegateする]
    #   引数: [self: commander]
    #   戻り値: [close result]
    #   副作用: [job runtime resourceを終了する]
    # }
    def close(self):
        return self._data.close()
