# Shared Job Queue — #221

The **Jobs** panel at the bottom of `KadokaTools.exe --new-ui` displays long-running Main GUI work through one GUI-independent job model.

## Current jobs

- `media_scan`: #219 folder scan. Total size is unknown before enumeration, so progress is `None`; discovered counts appear in the message and log.
- `tagger_probe`: #220 Tagger model/connectivity check.
- `tagger_tag`: #220 batches of 1–60 images. Progress is based on completed images.

Short display helpers such as thumbnails and Inspector previews are not jobs. Future ComfyUI, video, and LoRA work should use the same contract and explicit adapters.

## State and contract

The immutable `JobSnapshot` in `shared/contracts/job_contracts.py` is shared across UI, Process, and Data layers. It carries state (`queued / running / done / error / cancelled`), progress (`0..1` or `None`), timestamps, action and source metadata, a compact log (up to 50 lines of 400 characters), errors, and an optional external `backend_job_id`.

`retry_of` and `retryable` reserve retry lineage; current jobs are not retryable because their payloads are not persisted. History is limited to 100 jobs in memory; the oldest terminal jobs are removed first. History is not written to disk.

Backend adapters can call `register_backend_cancel_handler(job_id, handler)`. The runtime invokes the handler with the external ID on a user cancel or GUI shutdown. The handler must enqueue the request without blocking; network I/O belongs in the adapter worker. Callback errors are recorded in the job log and do not prevent local cooperative cancellation.

## Concurrency and cancellation

The shared `JobRuntime(max_concurrent=2)` limits Data-layer workers; later jobs remain queued. Media Scan and Tag processing share this limit.

- Cancelling a queued job marks it `cancelled` before work starts.
- Cancelling a running job signals its Event. Media Scan checks it in the scan loop; Tag HTTP stops before the next image after the current response or timeout.
- The runtime does not force-kill native, OS, or HTTP calls.
- GUI shutdown cancels queued jobs and signals running jobs without waiting for worker completion.

## UI and architecture

The Jobs panel shows state, progress, action, source, start time, and message. Details include IDs, completion time, compact logs, and errors. Stop is available for queued/running jobs. Retry remains disabled until a handler and payload retention are implemented. The UI Log tab remains separate from job logs.

Work stays in Data Processing (Media Scan / Tagger HTTP), which reports state to the shared Data-layer runtime. The UI only follows the Commander/Messenger path to `JobRuntime`; it does not import feature implementations directly.

## Validation

`tests/test_job_runtime.py` covers lifecycle, timestamps, progress/log/error, backend IDs and cancellation callbacks, history bounds, concurrency, cancellation, shutdown, and shared Media Scan/Tag jobs. `tests/test_job_queue_ui.py` covers multi-job display, progress, errors, logs, cancellation, and backend ID display. Windows completion-gate, UPD, app-boundary, and onedir shell smoke checks are also required for release validation.
