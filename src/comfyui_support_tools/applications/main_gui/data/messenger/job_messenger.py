"""Transport Job model requests without backend-specific interpretation."""

from comfyui_support_tools.applications.main_gui.data.commander.job_commander import (
    JobDataCommander,
)


class JobDataMessenger:
    def __init__(self, target: JobDataCommander):
        self._target = target

    def snapshots(self):
        return self._target.snapshots()

    def cancel(self, job_id):
        return self._target.cancel(job_id)

    # {
    #   責務: [pause: checkpoint可能なJobのpause要求をCommanderへ転送する]
    #   処理: [1: 対象Job IDをCommanderへ転送する]
    #   引数: [job_id: pauseするJob ID]
    #   戻り値: [requested: 要求受理状態]
    # }
    def pause(self, job_id):
        return self._target.pause(job_id)

    # {
    #   責務: [resume: paused Jobの再開要求をCommanderへ転送する]
    #   処理: [1: 対象Job IDをCommanderへ転送する]
    #   引数: [job_id: 再開するJob ID]
    #   戻り値: [resumed: 要求受理状態]
    # }
    def resume(self, job_id):
        return self._target.resume(job_id)

    # {
    #   責務: [retry: retry要求をData Commanderへ転送する]
    #   処理: [1: 対象Job IDを下位層へ転送する]
    #   引数: [job_id: retry元Job ID]
    #   戻り値: [retry_job_id: child Job IDまたはNone]
    # }
    def retry(self, job_id):
        return self._target.retry(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._target.close()
