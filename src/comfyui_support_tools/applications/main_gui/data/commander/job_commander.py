"""Expose the shared Data-layer JobRuntime through its boundary."""

from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime


class JobDataCommander:
    def __init__(self, runtime: JobRuntime):
        self._runtime = runtime

    def snapshots(self):
        return self._runtime.snapshots()

    def cancel(self, job_id):
        return self._runtime.cancel(job_id)

    # {
    #   責務: [pause: checkpoint可能なJobのpause要求をruntimeへ渡す]
    #   処理: [1: 対象Job IDをruntimeへ転送する]
    #   引数: [job_id: pauseするJob ID]
    #   戻り値: [requested: 要求受理状態]
    # }
    def pause(self, job_id):
        return self._runtime.pause(job_id)

    # {
    #   責務: [resume: paused Jobの再開要求をruntimeへ渡す]
    #   処理: [1: 対象Job IDをruntimeへ転送する]
    #   引数: [job_id: 再開するJob ID]
    #   戻り値: [resumed: 要求受理状態]
    # }
    def resume(self, job_id):
        return self._runtime.resume(job_id)

    # {
    #   責務: [retry: retry可能なJobをruntimeへ再実行要求する]
    #   処理: [1: 対象Job IDをruntimeへ転送する]
    #   引数: [job_id: retry元Job ID]
    #   戻り値: [retry_job_id: 作成されたchild Job ID、未対応ならNone]
    # }
    def retry(self, job_id):
        return self._runtime.retry(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._runtime.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._runtime.close()
