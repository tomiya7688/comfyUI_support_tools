"""Transport Job UI requests to the Process Commander."""
from comfyui_support_tools.applications.main_gui.process.commander.job_queue_commander import JobQueueCommander


class JobProcessMessenger:
    def __init__(self, target: JobQueueCommander):
        self._target = target

    def snapshots(self):
        return self._target.snapshots()

    def cancel(self, job_id):
        return self._target.cancel(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._target.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._target.close()
