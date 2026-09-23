"""Coordinate Job list commands; execution remains inside Data adapters."""
from comfyui_support_tools.applications.main_gui.process.messenger.job_data_messenger import JobDataRequests


class JobQueueCommander:
    def __init__(self, data: JobDataRequests):
        self._data = data

    def snapshots(self):
        return self._data.snapshots()

    def cancel(self, job_id):
        return self._data.cancel(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._data.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._data.close()
