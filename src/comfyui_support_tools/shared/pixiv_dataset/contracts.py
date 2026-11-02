"""Pixiv source, query, provenance, and download job contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


# {
# 責務: [PixivWork: preserve normalized work metadata returned by a source adapter]
# フィールド: [identity, creator, content, rights signals, source query, original API payload]
# }
@dataclass(frozen=True)
class PixivWork:
    work_id: str
    title: str
    user_id: str
    user_name: str
    work_type: str
    page_count: int
    tags: tuple[str, ...]
    description: str = ""
    creation_date: str = ""
    bookmark_count: int | None = None
    view_count: int | None = None
    restriction: int | None = None
    ai_type: int | None = None
    image_urls: tuple[str, ...] = ()
    ugoira_url: str | None = None
    ugoira_frames: tuple[tuple[str, int], ...] = ()


# {
# 責務: [PixivQueryPreset: describe a reusable search, creator, bookmark, ranking, or ID query]
# フィールド: [filters, destination, transfer options]
# }
@dataclass(frozen=True)
class PixivQueryPreset:
    name: str
    mode: str
    query: str = ""
    user_id: str = ""
    work_ids: tuple[str, ...] = ()
    filters: tuple[tuple[str, object], ...] = ()
    destination: str = ""
    download_original: bool = True
    include_manga: bool = True
    include_ugoira: bool = True
    convert_ugoira_preview: bool = False
    ugoira_preview_format: str = "gif"
    duplicate_policy: str = "group"
    rate_limit: PixivRateLimitProfile | None = None


# {
# 責務: [PixivDownloadResult: persist the outcome and integrity metadata for a work]
# フィールド: [work metadata, files, hashes, duplicate groups, status, timestamps]
# }
@dataclass(frozen=True)
class PixivDownloadResult:
    work: PixivWork
    files: tuple[str, ...]
    hashes: tuple[str, ...]
    status: str
    downloaded_at: str
    error: str = ""
    exact_duplicate_of: str = ""
    near_duplicate_of: str = ""


# {
# 責務: [PixivRateLimitProfile: store configurable API and download pacing policy]
# フィールド: [preset, interval, requests/minute, concurrency, retry/backoff, cooldown, pause threshold]
# 処理: [validate conservative defaults and expose custom-rate warning state]
# }
@dataclass(frozen=True)
class PixivRateLimitProfile:
    preset: str = "conservative"
    min_request_interval: float = 1.0
    max_requests_per_minute: int = 30
    api_concurrency: int = 1
    download_concurrency: int = 1
    retry_count: int = 3
    backoff_initial: float = 1.0
    backoff_max: float = 30.0
    jitter: float = 0.2
    cooldown_429: float = 60.0
    cooldown_repeated_errors: float = 60.0
    automatic_pause_after_failures: int = 5

    # {
    # 責務: [__post_init__: reject unbounded or non-finite rate-limit values]
    # 処理: [validate supported presets, throughput caps, retry and cooldown policy]
    # 引数: [self: immutable rate profile]
    # 戻り値: [None: validated policy]
    # }
    def __post_init__(self):
        numeric = (
            self.min_request_interval,
            self.backoff_initial,
            self.backoff_max,
            self.jitter,
            self.cooldown_429,
            self.cooldown_repeated_errors,
        )
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in numeric
        ):
            raise ValueError("rate-limit delays must be finite numbers")
        if self.preset not in {"conservative", "normal", "custom"}:
            raise ValueError("rate-limit preset must be conservative, normal, or custom")
        if not 0 <= self.min_request_interval <= 3600:
            raise ValueError("minimum request interval must be within 0..3600 seconds")
        if not 1 <= self.max_requests_per_minute <= 6000:
            raise ValueError("maximum requests per minute must be within 1..6000")
        if not 1 <= self.api_concurrency <= 16 or not 1 <= self.download_concurrency <= 16:
            raise ValueError("API and download concurrency must be within 1..16")
        if not 0 <= self.retry_count <= 10:
            raise ValueError("retry count must be within 0..10")
        if not 0 <= self.backoff_initial <= self.backoff_max <= 3600:
            raise ValueError("backoff must be finite and within 0..3600 seconds")
        if not 0 <= self.jitter <= 1:
            raise ValueError("retry jitter must be within 0..1")
        if not 0 <= self.cooldown_429 <= 3600 or not 0 <= self.cooldown_repeated_errors <= 3600:
            raise ValueError("cooldowns must be within 0..3600 seconds")
        if not 1 <= self.automatic_pause_after_failures <= 100:
            raise ValueError("automatic pause threshold must be within 1..100 failures")
        if self.preset == "conservative" and (
            self.min_request_interval < 1.0
            or self.max_requests_per_minute > 30
            or self.api_concurrency > 1
            or self.download_concurrency > 1
        ):
            raise ValueError("conservative preset cannot exceed its declared request limits")
        if self.preset == "normal" and (
            self.min_request_interval < 1.0
            or self.max_requests_per_minute > 60
            or self.api_concurrency > 2
            or self.download_concurrency > 2
        ):
            raise ValueError("normal preset cannot exceed its declared request limits")

    # {
    # 責務: [requires_custom_warning: identify aggressive user-selected request rates]
    # 処理: [flag rates exceeding conservative defaults for the UI to explain]
    # 引数: [None: reads effective profile]
    # 戻り値: [bool: caller should show rate-limit warning]
    # }
    @property
    def requires_custom_warning(self):
        return (
            self.min_request_interval < 1.0
            or self.max_requests_per_minute > 30
            or self.api_concurrency > 1
            or self.download_concurrency > 1
        )


# {
# 責務: [PixivSourceAdapter: keep the application independent of PixivPy3 API details]
# フィールド: [authentication, query modes, work details, original downloads]
# }
class PixivSourceAdapter(Protocol):
    # {
    # 責務: [authenticate: initialize an authorized user session]
    # 処理: [use refresh-token authentication without persisting the credential]
    # 引数: [refresh_token: user-provided token]
    # 戻り値: [None: session ready]
    # }
    def authenticate(self, refresh_token: str) -> None: ...

    # {
    # 責務: [health: verify the current account session]
    # 処理: [return a safe status without exposing tokens]
    # 引数: [None: uses current session]
    # 戻り値: [bool: session is usable]
    # }
    def health(self) -> bool: ...

    # {
    # 責務: [search_works: yield works matching source query]
    # 処理: [paginate according to source API and stop at the requested limit]
    # 引数: [query: source term, limit: maximum results]
    # 戻り値: [iterable[PixivWork]: discovered public/session-visible works]
    # }
    def search_works(self, query: str, limit: int): ...

    # {
    # 責務: [list_user_works: yield works visible for one creator]
    # 処理: [delegate access checks to the source API]
    # 引数: [user_id: Pixiv creator ID, limit: maximum results]
    # 戻り値: [iterable[PixivWork]: creator works]
    # }
    def list_user_works(self, user_id: str, limit: int): ...

    # {
    # 責務: [list_bookmarks: yield authenticated user's accessible bookmarks]
    # 処理: [respect API visibility and pagination]
    # 引数: [limit: maximum results]
    # 戻り値: [iterable[PixivWork]: bookmarked works]
    # }
    def list_bookmarks(self, limit: int, restrict: str = "public"): ...

    # {
    # 責務: [list_ranking: yield works in one supported ranking period]
    # 処理: [use the API's ranking endpoint]
    # 引数: [period: daily, weekly, or monthly, limit: maximum results]
    # 戻り値: [iterable[PixivWork]: ranked works]
    # }
    def list_ranking(self, period: str, limit: int): ...

    # {
    # 責務: [get_work: retrieve current authorized metadata and original URLs]
    # 処理: [obtain full page/ugoira data before download]
    # 引数: [work_id: Pixiv numeric work ID]
    # 戻り値: [PixivWork: normalized detail]
    # }
    def get_work(self, work_id: str) -> PixivWork: ...

    # {
    # 責務: [download_url: stream one original resource to a new local path]
    # 処理: [use PixivPy3's authorized request context]
    # 引数: [url: API-provided source URL, destination: temporary file path]
    # 戻り値: [None: file written]
    # }
    def download_url(self, url: str, destination: str) -> None: ...
