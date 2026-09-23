"""Carry Job state between Process and Data layers."""
from comfyui_support_tools.applications.main_gui.data.messenger.job_messenger import JobDataMessenger


class JobDataRequests:
    def __init__(self, target: JobDataMessenger):
        self._target = target

    def snapshots(self):
        return self._target.snapshots()

    def cancel(self, job_id):
        return self._target.cancel(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._target.close()
