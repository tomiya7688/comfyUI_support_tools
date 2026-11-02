"""Optional PixivPy3 adapter; importing the shared application needs no Pixiv dependency."""

from __future__ import annotations

import time
from pathlib import Path
from threading import BoundedSemaphore, Lock
from urllib.parse import parse_qs, urlparse

from .contracts import PixivRateLimitProfile, PixivWork


# {
# 責務: [PixivPy3Adapter: isolate PixivPy3 authentication and endpoint details]
# フィールド: [api client, session health]
# 処理: [normalize API payloads and expose only API-authorized content operations]
# }
class PixivPy3Adapter:
    # {
    # 責務: [__init__: accept an injected API client or lazily create PixivPy3]
    # 処理: [keep PixivPy3 optional for offline use and tests]
    # 引数: [api: optional compatible PixivPy3 AppPixivAPI]
    # 戻り値: [None: adapter ready]
    # }
    def __init__(self, api=None, request_interval=1.0, sleeper=time.sleep):
        if (
            not isinstance(request_interval, (int, float))
            or isinstance(request_interval, bool)
            or not 0 <= request_interval <= 3600
        ):
            raise ValueError("request interval must be within 0..3600 seconds")
        if api is None:
            try:
                from pixivpy3 import AppPixivAPI
            except ImportError as error:
                raise RuntimeError(
                    "Pixiv download requires the optional pixivpy3 package"
                ) from error
            api = AppPixivAPI()
        self.api = api
        self._authenticated = False
        self._user_id = ""
        self.request_interval = float(request_interval)
        self._sleep = sleeper
        self._last_request = 0.0
        self._throttle_lock = Lock()
        self._api_semaphore = BoundedSemaphore(1)
        self._download_semaphore = BoundedSemaphore(1)
        self.max_requests_per_minute = 30

    # {
    # 責務: [configure_rate_limit: apply effective per-job request pacing and concurrency caps]
    # 処理: [replace source request gates before each job starts]
    # 引数: [profile: validated effective rate profile]
    # 戻り値: [None: source gates updated]
    # }
    def configure_rate_limit(self, profile):
        if not isinstance(profile, PixivRateLimitProfile):
            raise ValueError("rate limit must be a PixivRateLimitProfile")
        self.request_interval = profile.min_request_interval
        self.max_requests_per_minute = profile.max_requests_per_minute
        self._api_semaphore = BoundedSemaphore(profile.api_concurrency)
        self._download_semaphore = BoundedSemaphore(profile.download_concurrency)

    # {
    # 責務: [authenticate: log in using refresh token]
    # 処理: [never store or return the provided credential]
    # 引数: [refresh_token: user-provided Pixiv refresh token]
    # 戻り値: [None: authenticated session]
    # }
    def authenticate(self, refresh_token):
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            raise ValueError("Pixiv refresh token is required")
        try:
            result = self._api_call(self.api.auth, refresh_token=refresh_token.strip())
        except Exception:
            raise RuntimeError("Pixiv authentication failed; check the refresh token") from None
        if _response_error(result):
            raise RuntimeError("Pixiv authentication failed; check the refresh token")
        response = result.get("response", {}) if isinstance(result, dict) else {}
        user = response.get("user", {}) if isinstance(response, dict) else {}
        self._user_id = str(
            getattr(self.api, "user_id", "")
            or (user.get("id", "") if isinstance(user, dict) else "")
        )
        self._authenticated = True

    # {
    # 責務: [health: verify session by reading the current account]
    # 処理: [convert API errors into a safe false result]
    # 引数: [None: current session]
    # 戻り値: [bool: authenticated session works]
    # }
    def health(self):
        if not self._authenticated:
            return False
        try:
            if self._user_id:
                result = self._api_call(self.api.user_detail, self._user_id)
            else:
                result = self._api_call(
                    self.api.user_bookmarks_illust,
                    "me",
                    restrict="public",
                    max_bookmark_id=None,
                )
        except Exception:
            return False
        return not _response_error(result)

    # {
    # 責務: [search_works: page tag search results up to a caller limit]
    # 処理: [request Pixiv's partial tag match and normalize results]
    # 引数: [query: tag query, limit: maximum works]
    # 戻り値: [tuple[PixivWork, ...]: matching works]
    # }
    def search_works(self, query, limit):
        if not self._authenticated:
            raise RuntimeError("Pixiv authentication is required")
        return self._collect(
            lambda offset: self._api_call(
                self.api.search_illust,
                query,
                search_target="partial_match_for_tags",
                offset=offset,
            ),
            limit,
        )

    # {
    # 責務: [list_user_works: page illustration and manga results by creator]
    # 処理: [call the authenticated user works endpoint]
    # 引数: [user_id: Pixiv numeric user ID, limit: maximum works]
    # 戻り値: [tuple[PixivWork, ...]: creator works]
    # }
    def list_user_works(self, user_id, limit):
        if not self._authenticated:
            raise RuntimeError("Pixiv authentication is required")
        results = []
        seen = set()
        for work_type in ("illust", "manga"):
            remaining = limit - len(results)
            if remaining <= 0:
                break
            page = self._collect(
                lambda offset, kind=work_type: self._api_call(
                    self.api.user_illusts, user_id, type=kind, offset=offset
                ),
                remaining,
            )
            for work in page:
                if work.work_id not in seen:
                    results.append(work)
                    seen.add(work.work_id)
        return tuple(results[:limit])

    # {
    # 責務: [list_bookmarks: page current user's accessible public bookmarks]
    # 処理: [use only bookmarks exposed by Pixiv's authenticated API]
    # 引数: [limit: maximum works]
    # 戻り値: [tuple[PixivWork, ...]: bookmarked works]
    # }
    def list_bookmarks(self, limit, restrict="public"):
        if not self._authenticated:
            raise RuntimeError("Pixiv authentication is required")
        if restrict not in {"public", "private"}:
            raise ValueError("bookmark restrict must be public or private")
        works, seen, cursor = [], set(), None
        while len(works) < limit:
            result = self._api_call(
                self.api.user_bookmarks_illust,
                self._user_id or "me",
                restrict=restrict,
                max_bookmark_id=cursor,
            )
            if _response_error(result):
                break
            for raw in result.get("illusts", ()):
                work = _normalize_work(raw)
                if work.work_id not in seen:
                    works.append(work)
                    seen.add(work.work_id)
                    if len(works) >= limit:
                        break
            next_url = result.get("next_url")
            parameters = parse_qs(urlparse(next_url).query) if next_url else {}
            next_cursor = parameters.get("max_bookmark_id", [None])[-1]
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return tuple(works)

    # {
    # 責務: [list_ranking: page works from a supported Pixiv ranking]
    # 処理: [restrict ranking period to the documented common values]
    # 引数: [period: daily, weekly, or monthly, limit: maximum works]
    # 戻り値: [tuple[PixivWork, ...]: ranked works]
    # }
    def list_ranking(self, period, limit):
        if not self._authenticated:
            raise RuntimeError("Pixiv authentication is required")
        aliases = {"daily": "day", "weekly": "week", "monthly": "month"}
        supported_modes = {
            "day",
            "week",
            "month",
            "day_male",
            "day_female",
            "day_manga",
            "week_original",
            "week_rookie",
            "day_r18",
            "day_male_r18",
            "day_female_r18",
            "week_r18",
            "week_r18g",
        }
        if period not in {*aliases, *supported_modes}:
            raise ValueError("ranking period must be daily, weekly, or monthly")
        mode = aliases.get(period, period)
        return self._collect(
            lambda offset: self._api_call(self.api.illust_ranking, mode, offset=offset), limit
        )

    # {
    # 責務: [get_work: read complete work metadata and original page URLs]
    # 処理: [resolve all manga/illustration pages and optional ugoira archive]
    # 引数: [work_id: numeric Pixiv work ID]
    # 戻り値: [PixivWork: normalized work]
    # }
    def get_work(self, work_id):
        if not self._authenticated:
            raise RuntimeError("Pixiv authentication is required")
        data = _payload(self._api_call(self.api.illust_detail, int(work_id)), "illust")
        work = _normalize_work(data)
        if work.work_type == "ugoira":
            metadata = _payload(
                self._api_call(self.api.ugoira_metadata, int(work_id)), "ugoira_metadata"
            )
            urls = metadata.get("zip_urls", {})
            frames = tuple(
                (str(frame.get("file", "")), int(frame.get("delay", 0)))
                for frame in metadata.get("frames", ())
                if isinstance(frame, dict) and frame.get("file")
            )
            return PixivWork(
                **{**work.__dict__, "ugoira_url": urls.get("original"), "ugoira_frames": frames}
            )
        pages = data.get("meta_pages") or ()
        urls = tuple(
            page.get("image_urls", {}).get("original") for page in pages if isinstance(page, dict)
        )
        if not urls:
            single = data.get("meta_single_page", {}).get("original_image_url")
            urls = (single,) if single else ()
        return PixivWork(**{**work.__dict__, "image_urls": urls})

    # {
    # 責務: [download_url: save one API-provided resource through PixivPy3]
    # 処理: [write into the caller's temporary directory]
    # 引数: [url: source URL returned by Pixiv API, destination: local file path]
    # 戻り値: [None: PixivPy3 wrote the resource]
    # }
    def download_url(self, url, destination):
        if not self._authenticated:
            raise RuntimeError("Pixiv authentication is required")
        try:
            parsed = urlparse(url) if isinstance(url, str) else None
            port = parsed.port if parsed else None
        except ValueError:
            parsed, port = None, None
        if (
            parsed is None
            or parsed.scheme != "https"
            or parsed.hostname != "i.pximg.net"
            or parsed.username
            or parsed.password
            or port
        ):
            raise ValueError("Pixiv resource URL must use the HTTPS image CDN")
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._api_call(
                self.api.download,
                url,
                path=str(path.parent),
                name=path.name,
                download=True,
            )
        except Exception as error:
            if (
                getattr(error, "status_code", None) == 429
                or getattr(error, "response", None) is not None
                and getattr(error.response, "status_code", None) == 429
            ):
                raise RuntimeError("Pixiv HTTP 429 rate limited") from None
            raise RuntimeError("Pixiv resource download failed") from None

    # {
    # 責務: [_collect: paginate Pixiv list endpoint results]
    # 処理: [use stable offsets, de-duplicate IDs, and stop on empty page]
    # 引数: [fetch: page function, limit: maximum result count]
    # 戻り値: [tuple[PixivWork, ...]: bounded normalized result list]
    # }
    def _collect(self, fetch, limit):
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise ValueError("result limit must be a positive integer")
        works, seen, offset = [], set(), 0
        while len(works) < limit:
            result = fetch(offset)
            if _response_error(result):
                break
            page = result.get("illusts", ()) if isinstance(result, dict) else ()
            if not page:
                break
            added = 0
            for raw in page:
                item = _normalize_work(raw)
                if item.work_id not in seen:
                    works.append(item)
                    seen.add(item.work_id)
                    added += 1
                    if len(works) >= limit:
                        break
            offset += len(page)
            if added == 0:
                break
        return tuple(works)

    # {
    # 責務: [_throttle: wait between Pixiv API and download requests]
    # 処理: [apply the configured minimum interval to every paginated request]
    # 引数: [None: reads configured interval and last request time]
    # 戻り値: [None: request interval satisfied]
    # }
    def _throttle(self):
        with self._throttle_lock:
            interval = max(self.request_interval, 60.0 / self.max_requests_per_minute)
            now = time.monotonic()
            delay = interval - (now - self._last_request)
            if delay > 0:
                self._sleep(delay)
            self._last_request = time.monotonic()

    # {
    # 責務: [_api_call: run one Pixiv request under concurrency and rate gates]
    # 処理: [serialize access to the client and select API/download concurrency]
    # 引数: [operation: PixivPy3 call, args/kwargs: API arguments, download: download gate selector]
    # 戻り値: [Any: PixivPy3 response or download result]
    # }
    def _api_call(self, operation, *args, download=False, **kwargs):
        semaphore = self._download_semaphore if download else self._api_semaphore
        with semaphore:
            self._throttle()
            return operation(*args, **kwargs)


# {
# 責務: [_normalize_work: validate and normalize a Pixiv API work object]
# 処理: [retain source data needed by downstream dataset preparation]
# 引数: [data: Pixiv illust object]
# 戻り値: [PixivWork: normalized work metadata]
# }
def _normalize_work(data):
    if not isinstance(data, dict) or not str(data.get("id", "")).isdigit():
        raise ValueError("Pixiv API returned a work without a numeric ID")
    user = data.get("user") or {}
    tags = data.get("tags") or ()
    try:
        type_id = int(data.get("type"))
    except (TypeError, ValueError):
        type_id = -1
    work_type = {0: "illustration", 1: "manga", 2: "ugoira"}.get(type_id, "unknown")
    normalized_tags = tuple(
        dict.fromkeys(
            str(tag.get("name", ""))
            for tag in tags
            if isinstance(tag, dict) and isinstance(tag.get("name"), str) and tag.get("name")
        )
    )
    title = str(data.get("title") or "")[:1000]
    description = str(data.get("caption") or "")[:100_000]
    return PixivWork(
        work_id=str(data["id"]),
        title=title,
        user_id=str(user.get("id") or "")[:64],
        user_name=str(user.get("name") or "")[:500],
        work_type=work_type,
        page_count=min(1000, max(1, int(data.get("page_count") or 1))),
        tags=normalized_tags,
        description=description,
        creation_date=str(data.get("create_date") or ""),
        bookmark_count=_optional_int(data.get("total_bookmarks")),
        view_count=_optional_int(data.get("total_view")),
        restriction=_optional_int(data.get("x_restrict")),
        ai_type=_optional_int(data.get("ai_type")),
    )


# {
# 責務: [_payload: unwrap API response data and detect errors without logging bodies]
# 処理: [avoid propagating response text that may contain sensitive server details]
# 引数: [response: PixivPy3 response, key: required response key]
# 戻り値: [dict: requested API payload]
# }
def _payload(response, key):
    if _response_error(response):
        raise RuntimeError("Pixiv API request failed")
    data = response.get("illust", response.get(key)) if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError("Pixiv API response is missing work metadata")
    return data


# {
# 責務: [_response_error: recognize a Pixiv API error response]
# 処理: [inspect status shape but never include response content in exceptions]
# 引数: [response: API response object]
# 戻り値: [bool: response indicates an error]
# }
def _response_error(response):
    if not isinstance(response, dict):
        return True
    return bool(response.get("error")) or response.get("status") == "failure"


# {
# 責務: [_optional_int: parse an optional numeric API field]
# 処理: [reject booleans and malformed values]
# 引数: [value: candidate field]
# 戻り値: [int | None: parsed value]
# }
def _optional_int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
