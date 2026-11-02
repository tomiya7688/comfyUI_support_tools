"""Composition root for the shared Main GUI Job Queue."""

import os
from pathlib import Path

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
from comfyui_support_tools.shared.job_snapshot_store import JobSnapshotStore


# {
#   責務: [default_job_store_path: OS標準state directory内のJob DB pathを決める]
#   処理: [1: 明示state dirを読む 2: OS固有state dirを選ぶ 3: DB pathを返す]
#   引数: []
#   戻り値: [path: persistent Job snapshot DB]
# }
def default_job_store_path() -> Path:
    configured_root = os.environ.get("COMFYUI_SUPPORT_TOOLS_STATE_DIR", "").strip()
    if configured_root:
        root = Path(configured_root).expanduser()
    elif os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "comfyui_support_tools" / "jobs.sqlite3"


# {
#   責務: [create_job_runtime: durable snapshot store付きshared Job runtimeを構築する]
#   処理: [1: concurrency上限を設定する 2: SQLite snapshot storeを注入する]
#   引数: [max_concurrent: 最大同時Job数, store_path: テストまたはportable環境向けDB path override]
#   戻り値: [runtime: GUI/CLI共通Job runtime]
# }
def create_job_runtime(
    max_concurrent: int = 2,
    *,
    store_path: Path | None = None,
) -> JobRuntime:
    store = JobSnapshotStore(store_path or default_job_store_path())
    return JobRuntime(max_concurrent=max_concurrent, store=store)


def create_job_queue(runtime: JobRuntime) -> JobQueueUiCommander:
    data = JobDataRequests(JobDataMessenger(JobDataCommander(runtime)))
    process = JobProcessMessenger(JobQueueCommander(data))
    return JobQueueUiCommander(JobUiMessenger(process))
