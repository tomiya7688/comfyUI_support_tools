"""Composition root for the shared Main GUI Job Queue."""

from comfyui_support_tools.applications.main_gui.data.commander.job_commander import (
    JobDataCommander,
)
from comfyui_support_tools.applications.main_gui.data.messenger.job_messenger import (
    JobDataMessenger,
)
from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime
from comfyui_support_tools.applications.main_gui.process.messenger.job_data_messenger import (
    JobDataRequests,
)
from comfyui_support_tools.applications.main_gui.process.commander.job_queue_commander import (
    JobQueueCommander,
)
from comfyui_support_tools.applications.main_gui.process.messenger.job_queue_messenger import (
    JobProcessMessenger,
)
from comfyui_support_tools.applications.main_gui.ui.messenger.job_queue_messenger import (
    JobUiMessenger,
)
from comfyui_support_tools.applications.main_gui.ui.commander.job_queue_commander import (
    JobQueueUiCommander,
)


# {
#   責務: [create_job_runtime: Main GUI用shared job runtimeを生成する]
#   処理: [指定同時実行数でJobRuntimeを初期化する]
#   引数: [max_concurrent: 並行実行job数。defaultは2]
#   戻り値: [JobRuntime: job stateとworkerを所有するruntime]
#   エラー: [JobRuntime初期化時のvalidation error]
# }
def create_job_runtime(max_concurrent: int = 2) -> JobRuntime:
    return JobRuntime(max_concurrent=max_concurrent)


# {
#   責務: [create_job_queue: runtimeをdata/process/UI層へ接続したqueue commanderを作る]
#   処理: [job commander/request/messengerを順に組み立ててruntimeへ接続する]
#   引数: [runtime: job lifecycleを共有するJobRuntime]
#   戻り値: [JobQueueUiCommander: UI層のjob queue操作入口]
# }
def create_job_queue(runtime: JobRuntime) -> JobQueueUiCommander:
    data = JobDataRequests(JobDataMessenger(JobDataCommander(runtime)))
    process = JobProcessMessenger(JobQueueCommander(data))
    return JobQueueUiCommander(JobUiMessenger(process))
