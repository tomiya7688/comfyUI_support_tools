"""Transport Job model requests without backend-specific interpretation."""
from comfyui_support_tools.applications.main_gui.data.commander.job_commander import JobDataCommander


class JobDataMessenger:
    def __init__(self, target: JobDataCommander):
        self._target = target

    def snapshots(self):
        return self._target.snapshots()

    def cancel(self, job_id):
        return self._target.cancel(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._target.close()
