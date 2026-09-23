"""Composition root for the shared Main GUI Job Queue."""
from comfyui_support_tools.applications.main_gui.data.commander.job_commander import JobDataCommander
from comfyui_support_tools.applications.main_gui.data.messenger.job_messenger import JobDataMessenger
from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime
from comfyui_support_tools.applications.main_gui.process.messenger.job_data_messenger import JobDataRequests
from comfyui_support_tools.applications.main_gui.process.commander.job_queue_commander import JobQueueCommander
from comfyui_support_tools.applications.main_gui.process.messenger.job_queue_messenger import JobProcessMessenger
from comfyui_support_tools.applications.main_gui.ui.messenger.job_queue_messenger import JobUiMessenger
from comfyui_support_tools.applications.main_gui.ui.commander.job_queue_commander import JobQueueUiCommander


def create_job_runtime(max_concurrent: int = 2) -> JobRuntime:
    return JobRuntime(max_concurrent=max_concurrent)


def create_job_queue(runtime: JobRuntime) -> JobQueueUiCommander:
    data = JobDataRequests(JobDataMessenger(JobDataCommander(runtime)))
    process = JobProcessMessenger(JobQueueCommander(data))
    return JobQueueUiCommander(JobUiMessenger(process))
