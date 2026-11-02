# Shared Job Queue — #221

The **Jobs** panel at the bottom of `KadokaTools.exe --new-ui` displays long-running Main GUI work through one GUI-independent job model.

## Current jobs

- `media_scan`: #219 folder scan. Total size is unknown before enumeration, so progress is `None`; discovered counts appear in the message and log.
- `tagger_probe`: #220 Tagger model/connectivity check.
- `tagger_tag`: #220 batches of 1–60 images. Progress is based on completed images.

Short display helpers such as thumbnails and Inspector previews are not jobs. Future ComfyUI, video, and LoRA work should use the same contract and explicit adapters.

## State and contract

The immutable `JobSnapshot` in `shared/contracts/job_contracts.py` is shared across UI, Process, Data, and CLI layers. Its lifecycle includes `queued / preparing / running / pausing / paused / cancelling / cancelled / resuming / retrying / done / failed / interrupted`; legacy adapters may still use `error`. It also carries progress, timestamps, action/source metadata, bounded logs, external IDs, capabilities, checkpoint and manifest references, completed/pending/failed items, and artifact references.

Cancellation capabilities are `cooperative`, `process`, `backend`, or `none`. Checkpoint capabilities are `none`, `stage`, `item`, or `native`; adapters call `checkpoint`, then `wait_if_paused`, and the controller calls `resume`. Shutdown policy is chosen per job: `cancel`, `finish_current_item`, `checkpoint_and_stop`, or `detach`. Partial-result policy is `keep`, `quarantine`, or `rollback`.

`retry_of`, `retryable`, `operation_id`, and `manifest_ref` define the retry contract. A registered retry handler must create a child with the same operation ID and the parent ID; repeated retry requests return the existing child. A registered resume handler reloads the operation from its Run Manifest after process restart. The runtime persists snapshots (not duplicated payloads) in SQLite, up to 100 jobs, under the OS state directory. `COMFYUI_SUPPORT_TOOLS_STATE_DIR` overrides the default path. The manifest owns inputs and idempotency/artifact records; the snapshot stores only their references.

Process and backend adapters can call `register_cancel_handler(job_id, handler, capability)` (`process` or `backend`). The runtime invokes the handler with the external ID on a user cancel or GUI shutdown. The handler must enqueue the request without blocking; process termination or network I/O belongs in the adapter worker. Callback errors are recorded in the job log and do not prevent local cooperative cancellation. The previous `register_backend_cancel_handler` name remains compatible.

## Concurrency and cancellation

The shared `JobRuntime(max_concurrent=2)` limits Data-layer workers; later jobs remain queued. Media Scan and Tag processing share this limit.

- Cancelling a queued job marks it `cancelled` before work starts.
- Cancelling a running job signals its Event. Media Scan checks it in the scan loop; Tag HTTP stops before the next image after the current response or timeout.
- The runtime does not force-kill native, OS, or HTTP calls.
- GUI shutdown cancels queued jobs and signals running jobs without waiting for worker completion.
- `checkpoint_and_stop` preserves a checkpoint for the next process; `detach` leaves an external backend running and restores the job as interrupted.

## UI and architecture

The Jobs panel shows state, progress, action, source, start time, and message. Details include IDs, completion time, capabilities, checkpoint/manifest references, item counts, artifacts, logs, and errors. Pause/resume appears for checkpoint-capable jobs; retry appears for retryable terminal jobs. Restart recovery requires a kind-specific handler that reconstructs inputs from the Run Manifest. The UI Log tab remains separate from job logs.

Work stays in Data Processing (Media Scan / Tagger HTTP), which reports state to the shared Data-layer runtime. The UI only follows the Commander/Messenger path to `JobRuntime`; CLI adapters can use the same GUI-independent runtime contract directly.

## Validation

`tests/test_job_runtime.py` covers lifecycle, restart recovery, checkpoint/pause/resume, idempotent retry lineage, backend cancellation, shutdown policy, history bounds, concurrency, and shared Media Scan/Tag jobs. `tests/test_job_queue_ui.py` covers multi-job display, progress, errors, logs, cancellation, checkpoint controls, and backend ID display. Windows completion-gate, UPD, app-boundary, and onedir shell smoke checks are also required for release validation.
