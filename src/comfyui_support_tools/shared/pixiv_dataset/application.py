"""Resumable, provenance-preserving Pixiv dataset collection application."""

from __future__ import annotations

import os
import random
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .contracts import PixivDownloadResult, PixivRateLimitProfile
from .helpers import (
    _DuplicateIndex,
    _file_name,
    _is_pixiv_resource_url,
    _job_id,
    _matches_filters,
    _metadata,
    _now,
    _preset_fingerprint,
    _provenance,
    _read_state,
    _result_files_valid,
    _result_from_state,
    _result_to_state,
    _safe_error,
    _safe_job_id,
    _sha256,
    _validate_preset,
    _write_json_atomic,
    convert_ugoira_preview,
)


# {
# 責務: [RetryPolicy: bound transient request retries and cooldown]
# フィールド: [retry count, initial/max delay, jitter, HTTP 429 cooldown]
# }
@dataclass(frozen=True)
class RetryPolicy:
    retries: int = 3
    initial_backoff: float = 1.0
    maximum_backoff: float = 30.0
    jitter: float = 0.2
    cooldown_429: float = 60.0

    # {
    # 責務: [__post_init__: reject unsafe or unbounded retry settings]
    # 処理: [require finite delays and at most ten attempts]
    # 引数: [self: immutable policy]
    # 戻り値: [None: validated policy]
    # }
    def __post_init__(self):
        if not 0 <= self.retries <= 10:
            raise ValueError("retries must be within 0..10")
        if not 0 <= self.initial_backoff <= self.maximum_backoff <= 3600:
            raise ValueError("backoff values must be within 0..3600 seconds")
        if not 0 <= self.jitter <= 1 or not 0 <= self.cooldown_429 <= 3600:
            raise ValueError("jitter or 429 cooldown is outside supported bounds")


# {
# 責務: [PixivDatasetApplication: collect, filter, persist and hand off source works]
# フィールド: [source adapter, retry/rate settings, progress/cancellation callbacks]
# 処理: [resume jobs, save safe metadata, detect duplicates, expose #356 payloads]
# }
class PixivDatasetApplication:
    # {
    # 責務: [__init__: configure source, retry, throttle, and progress policy]
    # 処理: [avoid any network access or credential persistence during construction]
    # 引数: [source: Pixiv adapter, retry_policy: bounded retries, request_interval: minimum delay, progress: optional callback, cancellation: optional callback]
    # 戻り値: [None: application ready]
    # }
    def __init__(
        self,
        source,
        retry_policy=None,
        request_interval=1.0,
        max_download_bytes=2 * 1024 * 1024 * 1024,
        rate_limit_profile=None,
        progress=None,
        cancellation=None,
        sleeper=time.sleep,
        random_source=random.random,
    ):
        if not 0 <= request_interval <= 3600:
            raise ValueError("request interval must be within 0..3600 seconds")
        if (
            not isinstance(max_download_bytes, int)
            or isinstance(max_download_bytes, bool)
            or not 1 <= max_download_bytes <= 16 * 1024**3
        ):
            raise ValueError("maximum download size must be within 1 byte and 16 GiB")
        self.source = source
        self.request_interval = float(request_interval)
        self.max_download_bytes = max_download_bytes
        legacy_retry = retry_policy or RetryPolicy()
        self.default_rate_limit = rate_limit_profile or PixivRateLimitProfile(
            preset="conservative" if request_interval >= 1.0 else "custom",
            min_request_interval=float(request_interval),
            retry_count=legacy_retry.retries,
            backoff_initial=legacy_retry.initial_backoff,
            backoff_max=legacy_retry.maximum_backoff,
            jitter=legacy_retry.jitter,
            cooldown_429=legacy_retry.cooldown_429,
        )
        if not isinstance(self.default_rate_limit, PixivRateLimitProfile):
            raise ValueError("rate_limit_profile must be a PixivRateLimitProfile")
        self.retry_policy = legacy_retry
        self.effective_rate_limit = self.default_rate_limit
        self.progress = progress or (lambda _event: None)
        self.cancellation = cancellation or (lambda: False)
        self._sleep = sleeper
        self._random = random_source
        self._last_request = 0.0
        self._job_state_path = None
        self._job_state = {}

    # {
    # 責務: [authenticate: verify refresh token through the injected source]
    # 処理: [keep the credential in the call stack only]
    # 引数: [refresh_token: user-provided Pixiv token]
    # 戻り値: [bool: authenticated session passes health check]
    # }
    def authenticate(self, refresh_token):
        self._retry(self.source.authenticate, refresh_token)
        if not self._retry(self.source.health):
            raise RuntimeError("Pixiv authentication check failed")
        return True

    # {
    # 責務: [run: execute a bounded query and resume previously completed works]
    # 処理: [filter source results, checkpoint every work, retry transient failures, and honor cancellation]
    # 引数: [preset: saved query, refresh_token: ephemeral auth input, job_id: stable identifier, rate_limit_override: per-job policy]
    # 戻り値: [tuple[PixivDownloadResult, ...]: complete, skipped, or failed per-work outcomes]
    # }
    def run(self, preset, refresh_token=None, job_id=None, rate_limit_override=None):
        _validate_preset(preset)
        profile = self._configure_rate_limit(preset, rate_limit_override)
        if self.cancellation():
            raise RuntimeError("job cancelled")
        root, job_id, state_path, state = self._initialize_job(preset, job_id, profile)
        self._authenticate_or_fail(refresh_token, state_path, state)
        completed = state.get("works", {})
        discovered = self._discover_or_fail(preset, state_path, state)
        work_ids = tuple(dict.fromkeys(work.work_id for work in discovered))
        self.progress({"job_id": job_id, "state": "discovered", "count": len(work_ids)})
        results = []
        consecutive_failures = 0
        for index, work_id in enumerate(work_ids):
            if self.cancellation():
                state["status"] = "cancelled"
                state["finished_at"] = _now()
                _write_json_atomic(state_path, state)
                self.progress({"job_id": job_id, "state": "cancelled", "completed": len(results)})
                break
            prior = completed.get(work_id)
            if prior and prior.get("status") == "downloaded" and _result_files_valid(root, prior):
                results.append(_result_from_state(prior))
                self.progress({"job_id": job_id, "state": "skipped", "work_id": work_id})
                continue
            summary = next(item for item in discovered if item.work_id == work_id)
            if not _matches_filters(summary, dict(preset.filters)):
                self.progress({"job_id": job_id, "state": "filtered", "work_id": work_id})
                continue
            try:
                detail = (
                    summary
                    if summary.image_urls or summary.ugoira_url
                    else self._retry(self.source.get_work, work_id)
                )
                result = self._download_one(root, preset, detail, job_id)
            except Exception as error:
                # Surface a bounded diagnostic, never exception text which can contain a token.
                result = PixivDownloadResult(summary, (), (), "failed", _now(), _safe_error(error))
                self.progress({"job_id": job_id, "state": "failed", "work_id": work_id})
            results.append(result)
            consecutive_failures = consecutive_failures + 1 if result.status == "failed" else 0
            completed[work_id] = _result_to_state(result)
            state["works"] = completed
            _write_json_atomic(state_path, state)
            self.progress(
                {
                    "job_id": job_id,
                    "state": result.status,
                    "work_id": work_id,
                    "completed": index + 1,
                    "total": len(work_ids),
                }
            )
            if consecutive_failures >= profile.automatic_pause_after_failures:
                state["paused"] = True
                state["status"] = "auto_paused"
                _write_json_atomic(state_path, state)
                self.progress(
                    {
                        "job_id": job_id,
                        "state": "auto_paused",
                        "completed": index + 1,
                        "total": len(work_ids),
                    }
                )
                break
        if state.get("status") != "cancelled":
            state["status"] = "auto_paused" if state.get("paused") else "completed"
            state["finished_at"] = _now()
            _write_json_atomic(state_path, state)
        return tuple(results)

    # {
    # 責務: [_configure_rate_limit: resolve and apply effective profile precedence]
    # 処理: [select job override, query profile, app profile, then configure source and retry policy]
    # 引数: [preset: query settings, override: per-job setting]
    # 戻り値: [PixivRateLimitProfile: effective policy]
    # }
    def _configure_rate_limit(self, preset, override):
        profile = override or preset.rate_limit or self.default_rate_limit
        if not isinstance(profile, PixivRateLimitProfile):
            raise ValueError("effective rate limit must be a PixivRateLimitProfile")
        self.effective_rate_limit = profile
        self.request_interval = max(
            profile.min_request_interval, 60.0 / profile.max_requests_per_minute
        )
        self.retry_policy = RetryPolicy(
            profile.retry_count,
            profile.backoff_initial,
            profile.backoff_max,
            profile.jitter,
            profile.cooldown_429,
        )
        configure = getattr(self.source, "configure_rate_limit", None)
        if callable(configure):
            configure(profile)
        return profile

    # {
    # 責務: [_initialize_job: validate or create the resumable job checkpoint]
    # 処理: [bind the checkpoint to its query, restore work/retry state, and persist start time]
    # 引数: [preset: query definition, requested_id: optional stable ID, profile: effective rate settings]
    # 戻り値: [tuple[Path, str, Path, dict]: dataset root, job ID, state path, state]
    # }
    def _initialize_job(self, preset, requested_id, profile):
        requested_root = Path(preset.destination).expanduser()
        if requested_root.is_symlink():
            raise ValueError("dataset root cannot be a symlink")
        root = requested_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        job_id = _safe_job_id(requested_id or _job_id(preset))
        indexes = root / "indexes"
        if indexes.is_symlink():
            raise ValueError("dataset index directory cannot be a symlink")
        state_path = indexes / f"job-{job_id}.json"
        query_fingerprint = _preset_fingerprint(preset)
        self._duplicates = _DuplicateIndex(root)
        previous = _read_state(state_path)
        prior_works = previous.get("works", {})
        if not isinstance(prior_works, dict):
            raise ValueError("job checkpoint contains an invalid work map")
        retry_history = previous.get("retry_history", [])
        rate_limit_history = previous.get("rate_limit_history", [])
        if not isinstance(retry_history, list) or not isinstance(rate_limit_history, list):
            raise ValueError("job checkpoint contains invalid retry history")
        if prior_works and previous.get("query_fingerprint") != query_fingerprint:
            raise ValueError("job ID is already associated with a different query preset")
        state = {
            "schema_version": 1,
            "job_id": job_id,
            "query_fingerprint": query_fingerprint,
            "effective_rate_limit": asdict(profile),
            "started_at": previous.get("started_at", _now()),
            "last_execution_started_at": _now(),
            "retry_history": retry_history[-10000:],
            "rate_limit_history": rate_limit_history[-10000:],
            "works": prior_works,
        }
        self._job_state_path = state_path
        self._job_state = state
        _write_json_atomic(state_path, state)
        return root, job_id, state_path, state

    # {
    # 責務: [_authenticate_or_fail: verify session and safely checkpoint authentication errors]
    # 処理: [use ephemeral refresh token or existing session and redact failure details]
    # 引数: [refresh_token: optional user secret, state_path: job checkpoint, state: current job state]
    # 戻り値: [None: session verified or sanitized exception raised]
    # }
    def _authenticate_or_fail(self, refresh_token, state_path, state):
        try:
            if refresh_token is not None:
                self.authenticate(refresh_token)
            elif not self._retry(self.source.health):
                raise RuntimeError("Pixiv authentication is required")
        except Exception as error:
            state["status"] = "authentication_failed"
            state["error"] = _safe_error(error)
            state["finished_at"] = _now()
            _write_json_atomic(state_path, state)
            raise RuntimeError("Pixiv authentication failed") from None

    # {
    # 責務: [_discover_or_fail: run source query and persist sanitized query failures]
    # 処理: [save a bounded error type rather than a raw API response]
    # 引数: [preset: query to discover, state_path: job checkpoint, state: current job state]
    # 戻り値: [tuple[PixivWork, ...]: discovered normalized works]
    # }
    def _discover_or_fail(self, preset, state_path, state):
        try:
            return self._discover(preset)
        except Exception as error:
            state["status"] = "query_failed"
            state["error"] = _safe_error(error)
            state["finished_at"] = _now()
            _write_json_atomic(state_path, state)
            raise RuntimeError("Pixiv query failed") from None

    # {
    # 責務: [_discover: select a supported source query mode]
    # 処理: [use bounded API results or explicit numeric work IDs]
    # 引数: [preset: validated search preset]
    # 戻り値: [tuple[PixivWork, ...]: discovered source works]
    # }
    def _discover(self, preset):
        limit = int(dict(preset.filters).get("limit", 100))
        if preset.mode == "search":
            return self._retry(self.source.search_works, preset.query, limit)
        if preset.mode == "creator":
            return self._retry(self.source.list_user_works, preset.user_id, limit)
        if preset.mode == "bookmarks":
            restrict = dict(preset.filters).get("bookmark_restrict", "public")
            return self._retry(self.source.list_bookmarks, limit, restrict)
        if preset.mode == "ranking":
            return self._retry(self.source.list_ranking, preset.query or "daily", limit)
        return tuple(
            self._retry(self.source.get_work, work_id) for work_id in preset.work_ids[:limit]
        )

    # {
    # 責務: [_download_one: download one work into a resumable provenance folder]
    # 処理: [store ordered pages or ugoira source, verify hashes, preserve permissions as unknown, and write metadata]
    # 引数: [root: dataset root, preset: effective query, work: API detail, job_id: active job]
    # 戻り値: [PixivDownloadResult: persisted work outcome]
    # }
    def _download_one(self, root, preset, work, job_id):
        if not isinstance(work.work_id, str) or not work.work_id.isdigit():
            raise ValueError("source returned an invalid numeric work ID")
        if work.work_type == "manga" and not preset.include_manga:
            return PixivDownloadResult(work, (), (), "skipped", _now(), "manga disabled")
        if work.work_type == "ugoira" and not preset.include_ugoira:
            return PixivDownloadResult(work, (), (), "skipped", _now(), "ugoira disabled")
        directory = root / "works" / work.work_id
        if (root / "works").is_symlink() or directory.is_symlink():
            raise ValueError("work storage directories cannot be symlinks")
        images = directory / "images"
        images.mkdir(parents=True, exist_ok=True)
        if images.is_symlink():
            raise ValueError("work image directory cannot be a symlink")
        checkpoint_path = directory / "download.json"
        checkpoint = _read_state(checkpoint_path)
        urls = (work.ugoira_url,) if work.work_type == "ugoira" else work.image_urls
        if not urls or len(urls) > 1000 or any(not _is_pixiv_resource_url(url) for url in urls):
            raise ValueError("work contains no valid original file URLs")
        files, hashes = [], []
        for page, url in enumerate(urls):
            if self.cancellation():
                break
            if not preset.download_original and work.work_type != "ugoira":
                continue
            name = _file_name(url, work, page)
            destination = images / name
            saved = checkpoint.get("files", {}).get(name)
            if saved and destination.is_file() and not destination.is_symlink():
                digest = _sha256(destination)
                if digest == saved.get("sha256"):
                    files.append(str(destination.relative_to(root)))
                    hashes.append(digest)
                    continue
            with tempfile.TemporaryDirectory(prefix=".pixiv-download-", dir=images) as temporary:
                partial = Path(temporary) / name
                self._retry(self.source.download_url, url, str(partial))
                if not partial.is_file() or partial.stat().st_size == 0:
                    raise OSError("Pixiv resource download produced no data")
                if partial.stat().st_size > self.max_download_bytes:
                    raise OSError("Pixiv resource exceeds the configured file size limit")
                if destination.exists() or destination.is_symlink():
                    raise FileExistsError(f"refusing to overwrite existing work file: {name}")
                digest = _sha256(partial)
                os.replace(partial, destination)
            checkpoint.setdefault("files", {})[name] = {
                "sha256": digest,
                "bytes": destination.stat().st_size,
            }
            _write_json_atomic(checkpoint_path, checkpoint)
            files.append(str(destination.relative_to(root)))
            hashes.append(digest)
            self.progress({"job_id": job_id, "state": "downloaded_file", "work_id": work.work_id})
        if work.work_type == "ugoira" and preset.convert_ugoira_preview and files:
            archive = Path(root, files[0])
            preview = images / f"ugoira.{preset.ugoira_preview_format}"
            convert_ugoira_preview(
                archive, work.ugoira_frames, preview, preset.ugoira_preview_format
            )
            files.append(str(preview.relative_to(root)))
            hashes.append(_sha256(preview))
        downloaded_at = _now()
        exact_duplicate = self._duplicates.find_exact(hashes, work.work_id)
        near_duplicate = self._duplicates.find_near(root, files, work.work_id)
        result = PixivDownloadResult(
            work,
            tuple(files),
            tuple(hashes),
            "downloaded" if files and len(files) == len(urls) else "partial",
            downloaded_at,
            exact_duplicate_of=exact_duplicate,
            near_duplicate_of=near_duplicate,
        )
        _write_json_atomic(
            directory / "work.json", _metadata(result, preset, self.effective_rate_limit)
        )
        _write_json_atomic(
            directory / "provenance.json",
            _provenance(result, preset, job_id, self.effective_rate_limit),
        )
        self._duplicates.add(root, work.work_id, hashes, files)
        return result

    # {
    # 責務: [_retry: call a source operation with bounded exponential backoff]
    # 処理: [throttle each attempt, cool down on rate-limit failures, and stop after configured retries]
    # 引数: [operation: source API call, args: positional API arguments]
    # 戻り値: [Any: operation result]
    # }
    def _retry(self, operation, *args):
        for attempt in range(self.retry_policy.retries + 1):
            if self.cancellation():
                raise RuntimeError("job cancelled")
            now = time.monotonic()
            wait = max(0.0, self.request_interval - (now - self._last_request))
            if wait:
                self._sleep(wait)
            self._last_request = time.monotonic()
            try:
                return operation(*args)
            except Exception as error:
                retry_after = self.retry_policy.cooldown_429 if "429" in str(error) else 0.0
                exponential = min(
                    self.retry_policy.maximum_backoff,
                    self.retry_policy.initial_backoff * (2**attempt),
                )
                repeated_error_cooldown = (
                    self.effective_rate_limit.cooldown_repeated_errors if attempt >= 1 else 0.0
                )
                retrying = attempt < self.retry_policy.retries
                delay = (
                    max(retry_after, repeated_error_cooldown, exponential)
                    * (1 + self.retry_policy.jitter * self._random())
                    if retrying
                    else 0.0
                )
                entry = {
                    "at": _now(),
                    "operation": "pixiv_source_call",
                    "attempt": attempt + 1,
                    "error_type": type(error).__name__,
                    "rate_limited": retry_after > 0,
                    "delay_seconds": delay,
                    "retrying": retrying,
                }
                self._job_state.setdefault("retry_history", []).append(entry)
                if retry_after > 0:
                    self._job_state.setdefault("rate_limit_history", []).append(entry)
                for key in ("retry_history", "rate_limit_history"):
                    self._job_state[key] = self._job_state.get(key, [])[-10000:]
                if self._job_state_path is not None:
                    _write_json_atomic(self._job_state_path, self._job_state)
                self.progress(
                    {
                        "state": "retrying" if retrying else "request_failed",
                        "attempt": attempt + 1,
                        "rate_limited": retry_after > 0,
                    }
                )
                if not retrying:
                    raise
                self._sleep(delay)

    # {
    # 責務: [curator_handoff: convert downloaded results into #356-compatible records]
    # 処理: [retain work/creator grouping, original tags, restrictions, provenance and duplicate group]
    # 引数: [results: downloaded or partial works]
    # 戻り値: [tuple[dict, ...]: transport-neutral curator payload]
    # }
    @staticmethod
    def curator_handoff(results, duplicate_policy="group"):
        if duplicate_policy not in {"keep", "group", "exclude_from_training", "lower_weight"}:
            raise ValueError("unsupported duplicate policy")
        return tuple(
            {
                "work_id": result.work.work_id,
                "creator_id": result.work.user_id,
                "creator_name": result.work.user_name,
                "image_paths": result.files,
                "work_group": f"pixiv:{result.work.work_id}",
                "creator_group": f"pixiv-user:{result.work.user_id}",
                "raw_tags": result.work.tags,
                "title": result.work.title,
                "description": result.work.description,
                "restriction": result.work.restriction,
                "ai_type": result.work.ai_type,
                "duplicate_group": result.exact_duplicate_of or result.near_duplicate_of,
                "duplicate_policy": duplicate_policy,
                "download_status": result.status,
                "training_eligible": result.status == "downloaded"
                and not (
                    duplicate_policy == "exclude_from_training"
                    and (result.exact_duplicate_of or result.near_duplicate_of)
                ),
                "sample_weight": (
                    0.0
                    if result.status != "downloaded"
                    else 0.5
                    if duplicate_policy == "lower_weight"
                    and (result.exact_duplicate_of or result.near_duplicate_of)
                    else 1.0
                ),
                "training_permission": "unknown",
                "redistribution_permission": "unknown",
                "provenance": "pixiv",
            }
            for result in results
        )
