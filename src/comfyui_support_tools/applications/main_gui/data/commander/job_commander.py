"""Expose the shared Data-layer JobRuntime through its boundary."""
from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime


class JobDataCommander:
    def __init__(self, runtime: JobRuntime):
        self._runtime = runtime

    def snapshots(self):
        return self._runtime.snapshots()

    def cancel(self, job_id):
        return self._runtime.cancel(job_id)

    def set_backend_job_id(self, job_id, backend_job_id):
        return self._runtime.set_backend_job_id(job_id, backend_job_id)

    def close(self):
        return self._runtime.close()
