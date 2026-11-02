# Pixiv Dataset Downloader

`comfyui_support_tools.shared.pixiv_dataset` separates Pixiv API calls from dataset storage. `PixivPy3Adapter` lazily imports the optional dependency; tests can inject any object implementing `PixivSourceAdapter`. `PixivDatasetApplication` applies source filters, retries, throttling, cancellation, per-work checkpoints, metadata/provenance output, duplicate grouping, and the transport-neutral #356 handoff.

Install the API adapter only in the Python environment that runs the downloader:

```bash
python -m pip install -r requirements-pixiv.txt
```

Construct a preset and pass the refresh token at execution time. Do not place tokens in presets, job metadata, command-line arguments, logs, or dataset output. Production UI integration should obtain the secret through the host application's secret binding and pass it to `PixivDatasetApplication.run` only for the active job.

```python
from comfyui_support_tools.shared.pixiv_dataset import (
    PixivDatasetApplication,
    PixivPy3Adapter,
    PixivQueryPreset,
)

preset = PixivQueryPreset(
    name="landscape",
    mode="search",
    query="landscape",
    filters=(("limit", 100), ("min_bookmarks", 100)),
    destination="datasets/pixiv_landscape",
)
results = PixivDatasetApplication(PixivPy3Adapter()).run(
    preset,
    refresh_token=secret_store.get("PIXIV_REFRESH_TOKEN"),
)
```

Supported modes are `search`, `creator`, `bookmarks`, `ranking`, and `ids`. Filters include result limit, minimum bookmarks, creator, work type, restriction/AI type, inclusive date bounds, and required/excluded tags. Query presets are stored in a bounded JSON file with atomic replacement. `PixivRateLimitProfile` configures minimum spacing, maximum requests per minute, API/download concurrency caps, retries, exponential backoff, jitter, 429/repeated-error cooldown, and automatic pause after repeated work failures. Effective precedence is per-job override, query preset, application profile, then conservative defaults. Custom profiles that exceed the initial conservative rate expose `requires_custom_warning` for the UI to explain before starting. Effective settings are included in the job checkpoint, work metadata, and provenance; bounded retry/429 history and job timestamps are checkpointed for audit/resume. The existing `JobRuntime` can execute a query through `submit_pixiv_download`, with cancellation and progress snapshots.

Files are stored under `works/<numeric-work-id>/images/`; each work has `work.json`, `provenance.json`, and a download checkpoint. `indexes/job-<id>.json` records job progress for resumption. Original downloads and previews are never overwritten; app-owned metadata and checkpoint JSON are atomically refreshed on resume. Training and redistribution rights are always recorded as `unknown`; download availability does not imply permission. Duplicate records are grouped for curator review and source files are retained.

Ugoira source ZIPs can optionally be converted to GIF or WebP previews using frame timing metadata. ZIP member paths, archive sizes, frame counts, and per-frame sizes are checked before conversion. The original archive remains intact. Perceptual grouping uses an average hash when Pillow can decode the image; exact grouping uses SHA-256. These are duplicate candidates and do not delete or exclude files automatically.

The shared backend can be tested offline with injected adapters. Live Pixiv authentication and network responses require a user-provided refresh token and are not part of automated tests. The repository does not yet provide a query-builder GUI, a CLI command, translated tag dictionaries, alternate non-original renditions, or MP4 conversion.
