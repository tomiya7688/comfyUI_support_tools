"""Coordinate Job list commands; execution remains inside Data adapters."""

from comfyui_support_tools.applications.main_gui.process.messenger.job_data_messenger import (
    JobDataRequests,
)


class JobQueueCommander:
    def __init__(self, data: JobDataRequests):
        self._data = data

    def snapshots(self):
        return self._data.snapshots()

    def cancel(self, job_id):
        return self._data.cancel(job_id)

    # {
    #   責務: [pause: checkpoint可能なJobのpause要求をDataへ伝える]
    #   処理: [1: 対象Job IDをDataへ転送する]
    #   引数: [job_id: pauseするJob ID]
    #   戻り値: [requested: 要求受理状態]
    # }
    def pause(self, job_id):
        return self._data.pause(job_id)

    # {
    #   責務: [resume: paused Jobの再開要求をDataへ伝える]
    #   処理: [1: 対象Job IDをDataへ転送する]
    #   引数: [job_id: 再開するJob ID]
    #   戻り値: [resumed: 要求受理状態]
    # }
    def resume(self, job_id):
        return self._data.resume(job_id)

    # {
    #   責務: [retry: retry可能なJobをDataへ再実行要求する]
    #   処理: [1: 対象Job IDをDataへ転送する]
    #   引数: [job_id: retry元Job ID]
    #   戻り値: [retry_job_id: child Job IDまたはNone]
    # }
    def retry(self, job_id):
        return self._data.retry(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._data.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._data.close()
