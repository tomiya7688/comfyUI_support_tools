"""Transport Job UI requests across the UI/Process boundary."""
from comfyui_support_tools.applications.main_gui.process.messenger.job_queue_messenger import JobProcessMessenger


class JobUiMessenger:
    def __init__(self, target: JobProcessMessenger):
        self._target = target

    def snapshots(self):
        return self._target.snapshots()

    def cancel(self, job_id):
        return self._target.cancel(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._target.close()
