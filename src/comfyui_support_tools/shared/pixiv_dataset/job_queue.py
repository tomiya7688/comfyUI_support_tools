"""Bridge Pixiv downloads to the application's existing bounded JobRuntime."""

from __future__ import annotations

from threading import Event, Lock, Thread

from .application import PixivDatasetApplication, RetryPolicy
from .contracts import PixivRateLimitProfile

_PIXIV_JOB_LOCK = Lock()


# {
# 責務: [submit_pixiv_download: register and run a Pixiv dataset task through JobRuntime]
# 処理: [support queued cancellation, progress snapshots, completion, and safe failure reporting]
# 引数: [runtime: existing JobRuntime, source: per-job adapter, preset: saved query, refresh_token: ephemeral user credential, retry_policy: bounded retries, request_interval: configured throttle]
# 戻り値: [str: runtime job ID]
# }
def submit_pixiv_download(
    runtime,
    source,
    preset,
    refresh_token=None,
    retry_policy=None,
    request_interval=1.0,
    rate_limit_override: PixivRateLimitProfile | None = None,
):
    cancel_event = Event()
    job_id = runtime.create(
        "pixiv_dataset",
        f"download:{preset.mode}",
        source_ids=preset.work_ids[:100],
        source_names=(preset.name,),
        cancel_event=cancel_event,
        retryable=True,
    )

    # {
    # 責務: [worker: wait for its queue slot and execute the cancellable application]
    # 処理: [map task events to bounded JobRuntime progress and terminal states]
    # 引数: [None: closes over one queued request]
    # 戻り値: [None: terminal snapshot recorded]
    # }
    def worker():
        if not runtime.wait_start(job_id):
            return

        # {
        # 責務: [report: map one downloader event to the bounded runtime snapshot]
        # 処理: [derive progress and sanitize event text before logging]
        # 引数: [event: downloader progress mapping]
        # 戻り値: [None: runtime snapshot updated]
        # }
        def report(event):
            state = event.get("state", "running")
            total = event.get("total") or event.get("count") or 0
            completed = event.get("completed", 0)
            progress = completed / total if total else None
            runtime.update(job_id, progress, state.replace("_", " "), state)

        try:
            app = PixivDatasetApplication(
                source,
                retry_policy=retry_policy or RetryPolicy(),
                request_interval=request_interval,
                rate_limit_profile=rate_limit_override,
                progress=report,
                cancellation=cancel_event.is_set,
            )
            with _PIXIV_JOB_LOCK:
                results = app.run(
                    preset,
                    refresh_token=refresh_token,
                    job_id=job_id,
                    rate_limit_override=rate_limit_override,
                )
            if cancel_event.is_set():
                runtime.finish(job_id, "cancelled", "Pixiv download cancelled")
            elif any(result.status == "failed" for result in results):
                runtime.finish(
                    job_id, "error", "Some Pixiv works failed", "Inspect per-work metadata"
                )
            else:
                runtime.finish(job_id, "done", f"Processed {len(results)} works")
        except Exception as error:
            if cancel_event.is_set():
                runtime.finish(job_id, "cancelled", "Pixiv download cancelled")
            else:
                runtime.finish(job_id, "error", "Pixiv download failed", type(error).__name__)

    Thread(target=worker, name=f"pixiv-{job_id}", daemon=True).start()
    return job_id
