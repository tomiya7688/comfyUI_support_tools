"""Pure metadata, checkpoint, duplicate, and file helpers for Pixiv collection."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from .contracts import PixivDownloadResult, PixivQueryPreset, PixivRateLimitProfile, PixivWork


# {
# 責務: [_validate_preset: validate a reusable query before filesystem/network activity]
# 処理: [bound input counts and reject unsupported source modes/options]
# 引数: [preset: candidate preset]
# 戻り値: [None: valid preset]
# }
def _validate_preset(preset):
    if not isinstance(preset, PixivQueryPreset):
        raise ValueError("query preset is required")
    if (
        not isinstance(preset.name, str)
        or not preset.name.strip()
        or len(preset.name) > 120
        or any(ord(char) < 32 for char in preset.name)
        or preset.mode not in {"search", "creator", "bookmarks", "ranking", "ids"}
    ):
        raise ValueError("query preset name or mode is invalid")
    if not preset.destination:
        raise ValueError("query preset destination is required")
    if not isinstance(preset.query, str) or not isinstance(preset.user_id, str):
        raise ValueError("query and user ID values must be strings")
    if preset.duplicate_policy not in {"keep", "group", "exclude_from_training", "lower_weight"}:
        raise ValueError("unsupported duplicate policy")
    if preset.ugoira_preview_format not in {"gif", "webp"}:
        raise ValueError("ugoira preview format must be gif or webp")
    if preset.rate_limit is not None and not isinstance(preset.rate_limit, PixivRateLimitProfile):
        raise ValueError("query preset rate limit must be a PixivRateLimitProfile")
    if preset.mode == "search" and (not isinstance(preset.query, str) or not preset.query.strip()):
        raise ValueError("tag search needs a query")
    if preset.mode == "creator" and (
        not isinstance(preset.user_id, str) or not preset.user_id.isdigit()
    ):
        raise ValueError("creator mode needs a numeric user ID")
    ranking_modes = {
        "",
        "daily",
        "weekly",
        "monthly",
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
    if preset.mode == "ranking" and preset.query not in ranking_modes:
        raise ValueError("unsupported ranking period")
    if preset.mode == "ids" and (
        not isinstance(preset.work_ids, (tuple, list))
        or not preset.work_ids
        or len(preset.work_ids) > 50000
        or any(not isinstance(item, str) or not item.isdigit() for item in preset.work_ids)
    ):
        raise ValueError("explicit work IDs must be numeric and bounded")
    if not isinstance(preset.filters, (tuple, list)) or any(
        not isinstance(item, (tuple, list)) or len(item) != 2 or not isinstance(item[0], str)
        for item in preset.filters
    ):
        raise ValueError("query filters must be key/value pairs")
    filters = dict(preset.filters)
    if len(filters) != len(preset.filters):
        raise ValueError("query filter keys must be unique")
    limit = filters.get("limit", 100)
    minimum = filters.get("min_bookmarks", 0)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50000:
        raise ValueError("query limit must be within 1..50000")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
        raise ValueError("minimum bookmark count must be non-negative")
    if filters.get("bookmark_restrict", "public") not in {"public", "private"}:
        raise ValueError("bookmark_restrict must be public or private")
    for key in ("include_tags", "exclude_tags"):
        tags = filters.get(key, ())
        if (
            not isinstance(tags, (tuple, list))
            or len(tags) > 1000
            or any(not isinstance(item, str) for item in tags)
        ):
            raise ValueError(f"{key} must be a bounded sequence of strings")
    for key in ("date_from", "date_to"):
        value = filters.get(key)
        if value is not None and (
            not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        ):
            raise ValueError(f"{key} must be an ISO date")
    if (
        filters.get("date_from")
        and filters.get("date_to")
        and filters["date_from"] > filters["date_to"]
    ):
        raise ValueError("date_from must not be later than date_to")
    for key in ("work_types", "restrictions", "ai_types"):
        value = filters.get(key)
        if value is not None and (not isinstance(value, (tuple, list)) or len(value) > 100):
            raise ValueError(f"{key} must be a bounded sequence")


# {
# 責務: [_matches_filters: apply reproducible source metadata filters]
# 処理: [filter creator, tags, bookmarks, dates, type, rating and AI origin]
# 引数: [work: discovered metadata, filters: selected filter values]
# 戻り値: [bool: work matches every active filter]
# }
def _matches_filters(work, filters):
    tags = {tag.casefold() for tag in work.tags}
    if filters.get("min_bookmarks", 0) and (
        work.bookmark_count is None or work.bookmark_count < filters["min_bookmarks"]
    ):
        return False
    if filters.get("creator_id") and work.user_id != str(filters["creator_id"]):
        return False
    if filters.get("work_types") and work.work_type not in filters["work_types"]:
        return False
    if filters.get("restrictions") is not None and work.restriction not in filters["restrictions"]:
        return False
    if filters.get("ai_types") is not None and work.ai_type not in filters["ai_types"]:
        return False
    includes = {item.casefold() for item in filters.get("include_tags", ())}
    excludes = {item.casefold() for item in filters.get("exclude_tags", ())}
    if includes and not includes.issubset(tags):
        return False
    if tags & excludes:
        return False
    date = work.creation_date[:10]
    if filters.get("date_from") and date < filters["date_from"]:
        return False
    if filters.get("date_to") and date > filters["date_to"]:
        return False
    return True


# {
# 責務: [_metadata: build bounded work JSON with no credential fields]
# 処理: [preserve raw/normalized tags, files, source query and original API facts]
# 引数: [result: downloaded work, preset: source query]
# 戻り値: [dict: versioned dataset work metadata]
# }
def _metadata(result, preset, rate_limit_profile):
    work = result.work
    return {
        "schema_version": 1,
        "work_id": work.work_id,
        "title": work.title,
        "user_id": work.user_id,
        "user_name": work.user_name,
        "work_type": work.work_type,
        "page_count": work.page_count,
        "tags": {
            "raw": list(work.tags),
            "normalized": list(dict.fromkeys(tag.strip() for tag in work.tags if tag.strip())),
        },
        "description": work.description,
        "creation_date": work.creation_date,
        "bookmark_count": work.bookmark_count,
        "view_count": work.view_count,
        "restriction": work.restriction,
        "ai_type": work.ai_type,
        "source_url": f"https://www.pixiv.net/artworks/{work.work_id}",
        "source_query": {
            "preset": preset.name,
            "mode": preset.mode,
            "query": preset.query,
            "filters": dict(preset.filters),
        },
        "effective_rate_limit": asdict(rate_limit_profile),
        "downloaded_at": result.downloaded_at,
        "local_files": list(result.files),
        "original_file_info": [
            {"path": path, "sha256": digest}
            for path, digest in zip(result.files, result.hashes, strict=False)
            if not (
                work.work_type == "ugoira" and Path(path).suffix.casefold() in {".gif", ".webp"}
            )
        ],
        "preview_files": [
            path
            for path in result.files
            if work.work_type == "ugoira" and Path(path).suffix.casefold() in {".gif", ".webp"}
        ],
        "download_status": result.status,
        "training_permission": "unknown",
        "redistribution_permission": "unknown",
        "exact_duplicate_of": result.exact_duplicate_of,
        "near_duplicate_of": result.near_duplicate_of,
        "duplicate_policy": preset.duplicate_policy,
    }


# {
# 責務: [_provenance: record source usage evidence without inferred rights]
# フィールド: [source IDs, query, timestamp, local hashes, permission states]
# 処理: [serialize provenance while preserving unknown permission decisions]
# 引数: [result: downloaded work, preset: effective query, job_id: resumable job identifier]
# 戻り値: [dict: versioned provenance document]
# }
def _provenance(result, preset, job_id, rate_limit_profile):
    return {
        "schema_version": 1,
        "source": "pixiv",
        "work_id": result.work.work_id,
        "creator_id": result.work.user_id,
        "source_url": f"https://www.pixiv.net/artworks/{result.work.work_id}",
        "query_preset_id": preset.name,
        "job_id": job_id,
        "effective_rate_limit": asdict(rate_limit_profile),
        "downloaded_at": result.downloaded_at,
        "local_hashes": list(result.hashes),
        "training_permission": "unknown",
        "redistribution_permission": "unknown",
        "notes": "Rights are not inferred from download availability.",
    }


# {
# 責務: [_write_json_atomic: atomically replace an application-owned JSON file]
# 処理: [reject symlink targets and write durable UTF-8 JSON through a sibling file]
# 引数: [path: output path, data: JSON-compatible value]
# 戻り値: [None: complete file installed]
# }
def _write_json_atomic(path, data):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("dataset metadata cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


# {
# 責務: [_read_state: safely load bounded resumable job metadata]
# 処理: [ignore missing, symlinked, oversized or malformed state]
# 引数: [path: job or download checkpoint]
# 戻り値: [dict: checkpoint or empty state]
# }
def _read_state(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


# {
# 責務: [_result_files_valid: verify prior job results before resuming past them]
# 処理: [confirm all recorded files still exist and match hashes]
# 引数: [root: dataset root, state: saved result]
# 戻り値: [bool: result can safely be reused]
# }
def _result_files_valid(root, state):
    files, hashes = state.get("files"), state.get("hashes")
    if (
        not isinstance(files, list)
        or not files
        or not isinstance(hashes, list)
        or len(files) != len(hashes)
    ):
        return False
    for name, expected in zip(files, hashes, strict=True):
        path = Path(root, name)
        try:
            path.resolve(strict=True).relative_to(Path(root).resolve(strict=True))
        except (ValueError, OSError):
            return False
        if path.is_symlink() or not path.is_file() or _sha256(path) != expected:
            return False
    return True


# {
# 責務: [_result_to_state: encode a completed work for crash-safe resumption]
# 処理: [convert typed fields into a JSON-safe checkpoint mapping]
# 引数: [result: per-work outcome]
# 戻り値: [dict: JSON-safe result state]
# }
def _result_to_state(result):
    return {
        "work": asdict(result.work),
        "files": list(result.files),
        "hashes": list(result.hashes),
        "status": result.status,
        "downloaded_at": result.downloaded_at,
        "error": result.error,
        "exact_duplicate_of": result.exact_duplicate_of,
        "near_duplicate_of": result.near_duplicate_of,
    }


# {
# 責務: [_result_from_state: restore typed result data from a job checkpoint]
# 処理: [reconstruct tuple fields and validated dataclass values]
# 引数: [state: persisted result mapping]
# 戻り値: [PixivDownloadResult: restored outcome]
# }
def _result_from_state(state):
    work_values = dict(state["work"])
    work_values["tags"] = tuple(work_values.get("tags", ()))
    work_values["image_urls"] = tuple(work_values.get("image_urls", ()))
    work_values["ugoira_frames"] = tuple(
        tuple(frame) for frame in work_values.get("ugoira_frames", ())
    )
    work = PixivWork(**work_values)
    return PixivDownloadResult(
        work,
        tuple(state["files"]),
        tuple(state["hashes"]),
        state["status"],
        state["downloaded_at"],
        state.get("error", ""),
        state.get("exact_duplicate_of", ""),
        state.get("near_duplicate_of", ""),
    )


# {
# 責務: [_DuplicateIndex: index exact and perceptual duplicates once per dataset run]
# フィールド: [sha256 owners, eight-band average-hash buckets]
# 処理: [avoid rescanning every metadata file after each downloaded work]
# }
class _DuplicateIndex:
    # {
    # 責務: [__init__: load existing work manifests into in-memory candidate indexes]
    # 処理: [index exact hashes and perceptual signatures once for the current dataset]
    # 引数: [root: dataset root]
    # 戻り値: [None: index populated]
    # }
    def __init__(self, root):
        self.root = Path(root)
        self.hash_owners = {}
        self.bands = {}
        manifests = sorted((self.root / "works").glob("*/work.json"))
        for manifest in manifests:
            if manifest.is_symlink() or manifest.parent.is_symlink():
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            work_id = manifest.parent.name
            self._add_hashes(
                work_id,
                (entry.get("sha256") for entry in data.get("original_file_info", ())),
            )
            for relative in data.get("local_files", ()):
                self._add_hash(work_id, _average_hash(self.root / relative))

    # {
    # 責務: [find_exact: return a different work sharing any SHA-256]
    # 処理: [lookup each current file digest in the in-memory owner map]
    # 引数: [hashes: local file digests, current_work: current work ID]
    # 戻り値: [str: matching work ID or empty]
    # }
    def find_exact(self, hashes, current_work):
        for digest in hashes:
            owner = self.hash_owners.get(digest)
            if owner and owner != current_work:
                return owner
        return ""

    # {
    # 責務: [find_near: match current perceptual hashes against indexed bands]
    # 処理: [use eight byte bands to bound candidate scans before exact Hamming comparison]
    # 引数: [root: dataset root, files: current work file paths, current_work: current work ID]
    # 戻り値: [str: candidate work ID or empty]
    # }
    def find_near(self, root, files, current_work):
        for relative in files:
            value = _average_hash(Path(root, relative))
            if value is None:
                continue
            candidates = set()
            for band in range(8):
                candidates.update(self.bands.get((band, (value >> (band * 8)) & 0xFF), ()))
            for work_id, existing in sorted(candidates):
                if work_id != current_work and (value ^ existing).bit_count() <= 6:
                    return work_id
        return ""

    # {
    # 責務: [add: add newly downloaded file hashes and perceptual signatures]
    # 処理: [update exact and near-duplicate indexes after metadata is persisted]
    # 引数: [root: dataset root, work_id: owning work, hashes: file hashes, files: relative paths]
    # 戻り値: [None: index updated]
    # }
    def add(self, root, work_id, hashes, files):
        self._add_hashes(work_id, hashes)
        for relative in files:
            self._add_hash(work_id, _average_hash(Path(root, relative)))

    # {
    # 責務: [_add_hashes: index SHA owners without replacing the first duplicate]
    # 処理: [retain the deterministic first owner for every exact hash]
    # 引数: [work_id: owning work, hashes: candidate digest iterable]
    # 戻り値: [None: hash index updated]
    # }
    def _add_hashes(self, work_id, hashes):
        for digest in hashes:
            if isinstance(digest, str) and digest:
                self.hash_owners.setdefault(digest, work_id)

    # {
    # 責務: [_add_hash: add one 64-bit perceptual signature to eight bands]
    # 処理: [insert signatures into each byte band for bounded candidate searches]
    # 引数: [work_id: owning work, value: average hash or None]
    # 戻り値: [None: band index updated]
    # }
    def _add_hash(self, work_id, value):
        if value is None:
            return
        for band in range(8):
            key = (band, (value >> (band * 8)) & 0xFF)
            self.bands.setdefault(key, set()).add((work_id, value))


# {
# 責務: [_average_hash: compute a small grayscale perceptual hash using Pillow]
# 処理: [return no signal when Pillow or a valid image decoder is unavailable]
# 引数: [path: local image]
# 戻り値: [int | None: 64-bit average hash]
# }
def _average_hash(path):
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as image:
            pixels = list(ImageOps.grayscale(image).resize((8, 8)).getdata())
        average = sum(pixels) / len(pixels)
        return sum((1 << index) for index, pixel in enumerate(pixels) if pixel >= average)
    except (ImportError, OSError, ValueError):
        return None


# {
# 責務: [_file_name: construct stable numeric page or archive file names]
# 処理: [ignore remote path traversal and unsupported suffixes]
# 引数: [url: original resource URL, work: work metadata, page: zero-based page index]
# 戻り値: [str: safe local basename]
# }
def _file_name(url, work, page):
    suffix = Path(urlparse(url).path).suffix.casefold()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".zip"}:
        suffix = ".zip" if work.work_type == "ugoira" else ".jpg"
    prefix = "ugoira" if work.work_type == "ugoira" else f"{page + 1:04d}"
    return f"{prefix}{suffix}"


# {
# 責務: [convert_ugoira_preview: convert a bounded Pixiv frame archive into GIF or WebP]
# 処理: [honor frame timing and reject archive traversal, oversized frames, and missing entries]
# 引数: [archive: downloaded ZIP, frames: ordered (filename, milliseconds), destination: preview path, output_format: gif or webp]
# 戻り値: [None: animated preview installed without replacing existing files]
# }
def convert_ugoira_preview(archive, frames, destination, output_format="gif"):
    if output_format not in {"gif", "webp"} or not frames or len(frames) > 2000:
        raise ValueError("ugoira conversion format or frame count is unsupported")
    archive = Path(archive)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("ugoira archive must be a bounded regular file")
    images, durations, total_size, total_pixels = [], [], 0, 0
    try:
        with zipfile.ZipFile(archive) as bundle:
            file_members = [item for item in bundle.infolist() if not item.is_dir()]
            if len(file_members) > 2000:
                raise ValueError("ugoira archive contains too many files")
            members = {Path(item.filename).name: item for item in file_members}
            for filename, duration in frames:
                if not filename or Path(filename).name != filename or filename not in members:
                    raise ValueError("ugoira frame metadata references an invalid archive path")
                info = members[filename]
                total_size += info.file_size
                if total_size > 2 * 1024 * 1024 * 1024 or info.file_size > 128 * 1024 * 1024:
                    raise ValueError("ugoira frames exceed the supported decoded size")
                from PIL import Image

                with Image.open(BytesIO(bundle.read(info))) as frame:
                    width, height = frame.size
                    total_pixels += width * height
                    if width > 16384 or height > 16384 or total_pixels > 25_000_000:
                        raise ValueError("ugoira frames exceed the supported pixel count")
                    images.append(frame.convert("RGBA"))
                if (
                    not isinstance(duration, int)
                    or isinstance(duration, bool)
                    or not 1 <= duration <= 60000
                ):
                    raise ValueError("ugoira frame duration is invalid")
                durations.append(duration)
    except (OSError, zipfile.BadZipFile, KeyError):
        raise ValueError("ugoira archive could not be decoded") from None
    if not images:
        raise ValueError("ugoira archive contains no frames")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("refusing to overwrite an existing ugoira preview")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    reserved = False
    try:
        descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        reserved = True
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
        images[0].save(
            temporary,
            format=output_format.upper(),
            save_all=True,
            append_images=images[1:],
            duration=durations,
            loop=0,
            disposal=2,
        )
        os.replace(temporary, destination)
        temporary = None
        reserved = False
    finally:
        for frame in images:
            frame.close()
        if temporary:
            temporary.unlink(missing_ok=True)
        if reserved:
            destination.unlink(missing_ok=True)


# {
# 責務: [_sha256: hash streamed file contents]
# 処理: [avoid loading full-resolution image bytes into memory]
# 引数: [path: file path]
# 戻り値: [str: SHA-256 digest]
# }
def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# {
# 責務: [_job_id: create a stable identifier for preset resumption]
# 処理: [hash non-secret query fields only]
# 引数: [preset: reusable query]
# 戻り値: [str: 16-character job identifier]
# }
def _job_id(preset):
    value = json.dumps(asdict(preset), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(value.encode()).hexdigest()[:16]


# {
# 責務: [_preset_fingerprint: bind resumable checkpoints to every effective query option]
# 処理: [hash a canonical secret-free preset representation]
# 引数: [preset: validated query]
# 戻り値: [str: SHA-256 fingerprint]
# }
def _preset_fingerprint(preset):
    value = json.dumps(asdict(preset), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(value.encode()).hexdigest()


# {
# 責務: [_safe_job_id: validate an optional job identifier before path composition]
# 処理: [allow portable alphanumeric, dash, and underscore only]
# 引数: [value: job identifier]
# 戻り値: [str: validated job identifier]
# }
def _safe_job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError("job ID must contain 1..64 portable characters")
    return value


# {
# 責務: [_safe_error: map exceptions to credential-safe diagnostic text]
# 処理: [do not serialize raw API exception messages]
# 引数: [error: caught exception]
# 戻り値: [str: safe error type]
# }
def _safe_error(error):
    return f"{type(error).__name__}: request failed"


# {
# 責務: [_is_pixiv_resource_url: restrict downloads to Pixiv's image CDN]
# 処理: [reject non-HTTPS URLs, URL credentials, alternate hosts, and explicit ports]
# 引数: [url: API-provided image URL]
# 戻り値: [bool: URL is safe for the authenticated downloader]
# }
def _is_pixiv_resource_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "i.pximg.net"
        and not parsed.username
        and not parsed.password
        and not port
    )


# {
# 責務: [_now: return a timezone-aware UTC timestamp]
# 処理: [serialize the current UTC time as ISO-8601]
# 引数: [None: current time]
# 戻り値: [str: ISO-8601 timestamp]
# }
def _now():
    return datetime.now(UTC).isoformat()
