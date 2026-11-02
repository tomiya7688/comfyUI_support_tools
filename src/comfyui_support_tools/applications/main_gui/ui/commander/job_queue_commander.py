"""UI-facing Job Queue contract."""

from comfyui_support_tools.applications.main_gui.ui.messenger.job_queue_messenger import (
    JobUiMessenger,
)


class JobQueueUiCommander:
    def __init__(self, target: JobUiMessenger):
        self._target = target

    def snapshots(self):
        return self._target.snapshots()

    def cancel(self, job_id):
        return self._target.cancel(job_id)

    # {
    #   責務: [pause: UIからのpause要求をJob runtime経路へ渡す]
    #   処理: [1: Job IDをUI Messengerへ転送する]
    #   引数: [job_id: pauseするJob ID]
    #   戻り値: [requested: 要求受理状態]
    # }
    def pause(self, job_id):
        return self._target.pause(job_id)

    # {
    #   責務: [resume: UIからのresume要求をJob runtime経路へ渡す]
    #   処理: [1: Job IDをUI Messengerへ転送する]
    #   引数: [job_id: 再開するJob ID]
    #   戻り値: [resumed: 要求受理状態]
    # }
    def resume(self, job_id):
        return self._target.resume(job_id)

    # {
    #   責務: [retry: UIのretry要求をJob runtime経路へ渡す]
    #   処理: [1: Job IDをUI Messengerへ転送する]
    #   引数: [job_id: retry元Job ID]
    #   戻り値: [retry_job_id: child Job IDまたはNone]
    # }
    def retry(self, job_id):
        return self._target.retry(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._target.close()
