"""End-to-end tests for Pixiv adapter isolation, provenance, and resumable downloads."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime
from comfyui_support_tools.shared.pixiv_dataset import (
    PixivDatasetApplication,
    PixivPy3Adapter,
    PixivQueryPreset,
    PixivQueryPresetStore,
    PixivRateLimitProfile,
    PixivWork,
    RetryPolicy,
    submit_pixiv_download,
)
from comfyui_support_tools.shared.pixiv_dataset.application import convert_ugoira_preview


# {
# 責務: [PixivDatasetTests: validate downloader features with local API and filesystem fixtures]
# フィールド: [temporary roots, fake Pixiv source, outcome assertions]
# 処理: [exercise authorization-safe metadata, retries, resume, and JobRuntime]
# }
class PixivDatasetTests(unittest.TestCase):
    # {
    # 責務: [make_work: create representative normalized Pixiv work metadata]
    # 処理: [provide raw tags, creator, restriction and multiple page URL fields]
    # 引数: [work_id: numeric ID, payload: bytes marker]
    # 戻り値: [PixivWork: fixture work]
    # }
    def make_work(self, work_id="101", payload="same"):
        return PixivWork(
            work_id,
            f"Title {work_id}",
            "42",
            "Creator",
            "illustration",
            1,
            ("landscape", "Original", "landscape"),
            "description",
            "2026-01-02T00:00:00+00:00",
            500,
            900,
            0,
            0,
            (f"https://i.pximg.net/{payload}.png",),
        )

    # {
    # 責務: [make_preset: create isolated query configurations for tests]
    # 処理: [build a valid typed query and apply selected test overrides]
    # 引数: [root: temporary dataset folder, mode: query mode]
    # 戻り値: [PixivQueryPreset: valid preset]
    # }
    def make_preset(self, root, mode="search", **kwargs):
        values = {
            "name": "landscape",
            "mode": mode,
            "query": "landscape" if mode in {"search", "ranking"} else "",
            "user_id": "42" if mode == "creator" else "",
            "work_ids": ("101", "102") if mode == "ids" else (),
            "filters": (("limit", 10),),
            "destination": str(root),
        }
        values.update(kwargs)
        return PixivQueryPreset(**values)

    # {
    # 責務: [test_download_saves_provenance_and_never_persists_credentials]
    # 処理: [download one work and inspect versioned metadata/provenance]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_download_saves_provenance_and_never_persists_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = FakePixivSource([self.make_work()])
            result = PixivDatasetApplication(source, sleeper=lambda _delay: None).run(
                self.make_preset(Path(temporary)),
                refresh_token="private-refresh-token",
                job_id="safe-job",
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].status, "downloaded")
            metadata = Path(temporary, "works", "101", "work.json").read_text(encoding="utf-8")
            provenance = Path(temporary, "works", "101", "provenance.json").read_text(
                encoding="utf-8"
            )
            checkpoint = Path(temporary, "indexes", "job-safe-job.json").read_text(encoding="utf-8")
            self.assertIn('"training_permission": "unknown"', metadata)
            self.assertIn('"redistribution_permission": "unknown"', provenance)
            self.assertIn('"tags": {', metadata)
            self.assertNotIn("private-refresh-token", metadata + provenance + checkpoint)
            self.assertEqual(len(result[0].hashes), 1)

    # {
    # 責務: [test_resume_reuses_verified_files_and_does_not_redownload]
    # 処理: [run the same stable job twice and validate its file checkpoint]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_resume_reuses_verified_files_and_does_not_redownload(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = FakePixivSource([self.make_work()])
            app = PixivDatasetApplication(source, sleeper=lambda _delay: None)
            preset = self.make_preset(Path(temporary))
            first = app.run(preset, job_id="resume-me")
            second = app.run(preset, job_id="resume-me")
            self.assertEqual(first, second)
            self.assertEqual(source.download_calls, 1)
            self.assertEqual(source.detail_calls, 0)

    # {
    # 責務: [test_resume_rejects_job_id_reused_for_a_different_query]
    # 処理: [protect saved results from being silently mixed with changed query settings]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_resume_rejects_job_id_reused_for_a_different_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = FakePixivSource([self.make_work()])
            app = PixivDatasetApplication(source, sleeper=lambda _delay: None)
            first = self.make_preset(Path(temporary))
            app.run(first, job_id="same-job")
            changed = PixivQueryPreset(**{**first.__dict__, "query": "different"})
            with self.assertRaises(ValueError):
                app.run(changed, job_id="same-job")

    # {
    # 責務: [test_source_filters_and_exact_duplicate_groups_are_reported]
    # 処理: [filter by bookmark/tag metadata and detect a duplicate page without deleting it]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_source_filters_and_exact_duplicate_groups_are_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = self.make_work("101"), self.make_work("102")
            filtered = self.make_work("103", payload="filtered")
            filtered = PixivWork(**{**filtered.__dict__, "tags": ("avoid",)})
            source = FakePixivSource([first, second, filtered])
            preset = self.make_preset(
                Path(temporary),
                mode="ids",
                work_ids=("101", "102", "103"),
                filters=(
                    ("limit", 10),
                    ("include_tags", ("landscape",)),
                    ("exclude_tags", ("avoid",)),
                ),
            )
            results = PixivDatasetApplication(source, sleeper=lambda _delay: None).run(preset)
            self.assertEqual([result.work.work_id for result in results], ["101", "102"])
            self.assertEqual(results[1].exact_duplicate_of, "101")
            self.assertTrue(Path(temporary, "works", "102", "images", "0001.png").is_file())
            handoff = PixivDatasetApplication.curator_handoff(
                results, duplicate_policy="exclude_from_training"
            )
            self.assertFalse(handoff[1]["training_eligible"])
            self.assertTrue(handoff[0]["training_eligible"])

    # {
    # 責務: [test_perceptual_hash_groups_similar_images_without_marking_them_exact]
    # 処理: [download distinct encoded images with a matching average hash]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_perceptual_hash_groups_similar_images_without_marking_them_exact(self):
        try:
            from PIL import Image  # noqa: F401
        except ImportError:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as temporary:
            works = [
                self.make_work("201", "red1"),
                self.make_work("202", "red2"),
            ]
            source = FakePixivSource(works)
            preset = self.make_preset(Path(temporary), mode="ids", work_ids=("201", "202"))
            results = PixivDatasetApplication(source, sleeper=lambda _delay: None).run(preset)
            self.assertEqual(results[1].exact_duplicate_of, "")
            self.assertEqual(results[1].near_duplicate_of, "201")

    # {
    # 責務: [test_failed_download_retry_is_bounded_and_exception_text_is_redacted]
    # 処理: [simulate a transient secret-bearing error and inspect persisted diagnostic]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_failed_download_retry_is_bounded_and_exception_text_is_redacted(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = FakePixivSource([self.make_work()], failures=4)
            sleeps = []
            app = PixivDatasetApplication(
                source,
                retry_policy=RetryPolicy(
                    retries=2, initial_backoff=0.1, maximum_backoff=0.2, jitter=0
                ),
                sleeper=sleeps.append,
            )
            results = app.run(self.make_preset(Path(temporary)), job_id="retry-job")
            self.assertEqual(results[0].status, "failed")
            self.assertEqual(source.download_calls, 3)
            self.assertNotIn("very-secret", results[0].error)
            self.assertGreaterEqual(len(sleeps), 2)
            checkpoint = Path(temporary, "indexes", "job-retry-job.json").read_text()
            self.assertIn('"started_at"', checkpoint)
            self.assertIn('"retrying": false', checkpoint)
            self.assertNotIn("very-secret", checkpoint)

    # {
    # 責務: [test_filtering_and_validation_reject_unsafe_input_before_network]
    # 処理: [reject symlink output roots and invalid IDs/rate settings]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_filtering_and_validation_reject_unsafe_input_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            target = base / "target"
            target.mkdir()
            link = base / "linked"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink creation is unavailable")
            source = FakePixivSource([])
            with self.assertRaises(ValueError):
                PixivDatasetApplication(source).run(self.make_preset(link))
            with self.assertRaises(ValueError):
                PixivDatasetApplication(source).run(
                    self.make_preset(base, mode="ids", work_ids=("../escape",))
                )
            self.assertEqual(source.search_calls, 0)

    # {
    # 責務: [test_preset_store_round_trips_queries_without_credentials]
    # 処理: [save/list/load and refuse implicit overwrite]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_preset_store_round_trips_queries_without_credentials(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary, "queries", "presets.json")
            store = PixivQueryPresetStore(path)
            profile = PixivRateLimitProfile(
                preset="custom", min_request_interval=0.5, max_requests_per_minute=30
            )
            preset = self.make_preset(
                Path(temporary),
                filters=(("limit", 5), ("include_tags", ("sky",))),
                rate_limit=profile,
            )
            store.save(preset)
            self.assertEqual(store.list(), ("landscape",))
            self.assertEqual(store.get("landscape"), preset)
            with self.assertRaises(FileExistsError):
                store.save(preset)
            self.assertNotIn("refresh_token", path.read_text(encoding="utf-8"))
            self.assertTrue(store.get("landscape").rate_limit.requires_custom_warning)

    # {
    # 責務: [test_repeated_work_failures_auto_pause_and_persist_effective_rate_policy]
    # 処理: [stop after configured consecutive failures and persist effective settings]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_repeated_work_failures_auto_pause_and_persist_effective_rate_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = FakePixivSource([self.make_work("101"), self.make_work("102")], failures=10)
            profile = PixivRateLimitProfile(
                preset="custom",
                min_request_interval=0,
                max_requests_per_minute=6000,
                retry_count=0,
                automatic_pause_after_failures=2,
            )
            events = []
            preset = self.make_preset(Path(temporary))
            results = PixivDatasetApplication(
                source,
                rate_limit_profile=profile,
                progress=events.append,
                sleeper=lambda _delay: None,
            ).run(preset, job_id="pause-job")
            state = json.loads(Path(temporary, "indexes", "job-pause-job.json").read_text())
            self.assertEqual(len(results), 2)
            self.assertTrue(state["paused"])
            self.assertEqual(state["effective_rate_limit"]["max_requests_per_minute"], 6000)
            self.assertIn("auto_paused", [event["state"] for event in events])

    # {
    # 責務: [test_rate_profile_precedence_prefers_job_override_and_rejects_mislabeled_fast_profile]
    # 処理: [verify job settings override query and application defaults in durable metadata]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_rate_profile_precedence_prefers_job_override_and_rejects_mislabeled_fast_profile(self):
        with self.assertRaises(ValueError):
            PixivRateLimitProfile(max_requests_per_minute=6000)
        with tempfile.TemporaryDirectory() as temporary:
            query_profile = PixivRateLimitProfile(
                preset="custom", min_request_interval=2, max_requests_per_minute=20
            )
            job_profile = PixivRateLimitProfile(
                preset="custom", min_request_interval=3, max_requests_per_minute=10
            )
            preset = self.make_preset(Path(temporary), rate_limit=query_profile)
            app = PixivDatasetApplication(
                FakePixivSource([self.make_work()]),
                rate_limit_profile=PixivRateLimitProfile(),
                sleeper=lambda _delay: None,
            )
            app.run(preset, job_id="rate-job", rate_limit_override=job_profile)
            metadata = json.loads(Path(temporary, "works", "101", "work.json").read_text())
            self.assertEqual(metadata["effective_rate_limit"]["max_requests_per_minute"], 10)

    # {
    # 責務: [test_pixivpy_adapter_normalizes_auth_search_pages_and_ugoira]
    # 処理: [exercise adapter endpoints with an injected local fake client]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_pixivpy_adapter_normalizes_auth_search_pages_and_ugoira(self):
        api = FakePixivApi()
        adapter = PixivPy3Adapter(api, request_interval=0, sleeper=lambda _delay: None)
        adapter.authenticate("token-not-retained")
        self.assertTrue(adapter.health())
        self.assertEqual(adapter.search_works("sky", 2)[0].work_id, "101")
        self.assertEqual(adapter.list_user_works("42", 2)[0].work_id, "101")
        self.assertEqual(
            [item.work_id for item in adapter.list_bookmarks(2, "private")], ["101", "102"]
        )
        self.assertEqual(adapter.list_ranking("weekly", 2)[0].work_id, "101")
        self.assertEqual(api.bookmark_restricts, ["private", "private"])
        self.assertEqual(api.ranking_modes[0], "week")
        work = adapter.get_work("202")
        self.assertEqual(work.work_type, "ugoira")
        self.assertEqual(work.ugoira_url, "https://i.pximg.net/ugoira.zip")
        self.assertEqual(work.ugoira_frames, (("000000.jpg", 80),))
        self.assertNotIn("token-not-retained", repr(adapter.__dict__))

    # {
    # 責務: [test_job_runtime_bridge_tracks_completion_and_cancellation]
    # 処理: [submit the downloader to the actual thread-safe queue and observe its terminal snapshot]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_job_runtime_bridge_tracks_completion_and_cancellation(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = JobRuntime(max_concurrent=1)
            job_id = submit_pixiv_download(
                runtime,
                FakePixivSource([self.make_work()]),
                self.make_preset(Path(temporary)),
                request_interval=0,
            )
            deadline = time.monotonic() + 5
            snapshot = runtime.snapshots()[0]
            while (
                snapshot.state not in {"done", "error", "cancelled"} and time.monotonic() < deadline
            ):
                time.sleep(0.01)
                snapshot = runtime.snapshots()[0]
            runtime.close()
            self.assertEqual(snapshot.id, job_id)
            self.assertEqual(snapshot.state, "done")
            self.assertEqual(snapshot.progress, 1.0)

    # {
    # 責務: [test_resource_download_rejects_non_pixiv_https_hosts]
    # 処理: [reject an adapter URL outside Pixiv CDN before any download call]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_resource_download_rejects_non_pixiv_https_hosts(self):
        with tempfile.TemporaryDirectory() as temporary:
            malicious = self.make_work()
            malicious = PixivWork(
                **{**malicious.__dict__, "image_urls": ("https://example.org/payload.png",)}
            )
            source = FakePixivSource([malicious])
            results = PixivDatasetApplication(source, sleeper=lambda _delay: None).run(
                self.make_preset(Path(temporary))
            )
            self.assertEqual(results[0].status, "failed")
            self.assertEqual(source.download_calls, 0)

    # {
    # 責務: [test_ugoira_preview_conversion_preserves_frame_order_and_timing]
    # 処理: [convert a tiny local frame archive and validate animated output]
    # 引数: [None: unittest scenario]
    # 戻り値: [None: assertions pass or raise]
    # }
    def test_ugoira_preview_conversion_preserves_frame_order_and_timing(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "ugoira.zip"
            frame = root / "000000.png"
            Image.new("RGB", (4, 4), "red").save(frame)
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.write(frame, "000000.jpg")
            output = root / "preview.gif"
            convert_ugoira_preview(archive, (("000000.jpg", 80),), output)
            self.assertTrue(output.is_file())
            with Image.open(output) as preview:
                self.assertEqual(preview.n_frames, 1)
                self.assertEqual(preview.info["duration"], 80)
            with self.assertRaises(FileExistsError):
                convert_ugoira_preview(archive, (("000000.jpg", 80),), output)


# {
# 責務: [FakePixivSource: supply deterministic API responses and download bytes]
# フィールド: [works, calls, transient failure counter]
# }
class FakePixivSource:
    # {
    # 責務: [__init__: store fake works and optional transient failures]
    # 処理: [initialize call counters and an ephemeral test session]
    # 引数: [works: result values, failures: number of initial download failures]
    # 戻り値: [None: fake adapter ready]
    # }
    def __init__(self, works, failures=0):
        self.works = {work.work_id: work for work in works}
        self.failures = failures
        self.download_calls = 0
        self.detail_calls = 0
        self.search_calls = 0
        self.token = ""

    # {
    # 責務: [authenticate: retain token only in the fake session]
    # 処理: [simulate successful refresh-token authentication]
    # 引数: [refresh_token: test token]
    # 戻り値: [None: fake logged in]
    # }
    def authenticate(self, refresh_token):
        self.token = refresh_token

    # {
    # 責務: [health: expose fake API session state]
    # 処理: [report an available deterministic fixture session]
    # 引数: [None: current test session]
    # 戻り値: [bool: session usable]
    # }
    def health(self):
        return True

    # {
    # 責務: [search_works: return the bounded fixture result set]
    # 処理: [count a search and return at most the requested fixture count]
    # 引数: [query: search, limit: result bound]
    # 戻り値: [tuple[PixivWork, ...]: fake works]
    # }
    def search_works(self, query, limit):
        self.search_calls += 1
        return tuple(self.works.values())[:limit]

    # {
    # 責務: [list_user_works: return creator fixture works]
    # 処理: [return a bounded deterministic creator result set]
    # 引数: [user_id: creator ID, limit: maximum]
    # 戻り値: [tuple[PixivWork, ...]: fake works]
    # }
    def list_user_works(self, user_id, limit):
        return tuple(self.works.values())[:limit]

    # {
    # 責務: [list_bookmarks: return bookmark fixture works]
    # 処理: [return a bounded deterministic bookmark result set]
    # 引数: [limit: maximum]
    # 戻り値: [tuple[PixivWork, ...]: fake works]
    # }
    def list_bookmarks(self, limit, restrict="public"):
        return tuple(self.works.values())[:limit]

    # {
    # 責務: [list_ranking: return ranking fixture works]
    # 処理: [return a bounded deterministic ranking result set]
    # 引数: [period: selected ranking, limit: maximum]
    # 戻り値: [tuple[PixivWork, ...]: fake works]
    # }
    def list_ranking(self, period, limit):
        return tuple(self.works.values())[:limit]

    # {
    # 責務: [get_work: read one fixture work]
    # 処理: [increment detail access count and return normalized work metadata]
    # 引数: [work_id: numeric identifier]
    # 戻り値: [PixivWork: fixture detail]
    # }
    def get_work(self, work_id):
        self.detail_calls += 1
        return self.works[str(work_id)]

    # {
    # 責務: [download_url: write fixture bytes to temporary output]
    # 処理: [simulate transient failure before a successful local write]
    # 引数: [url: fixture resource URL, destination: output path]
    # 戻り値: [None: file written or failure raised]
    # }
    def download_url(self, url, destination):
        self.download_calls += 1
        if self.failures:
            self.failures -= 1
            raise RuntimeError(f"very-secret token {self.token}")
        asset = url.rsplit("/", 1)[-1]
        if asset in {"red1.png", "red2.png"}:
            from PIL import Image

            color = (255, 0, 0) if asset == "red1.png" else (250, 0, 0)
            Image.new("RGB", (8, 8), color).save(destination)
        else:
            Path(destination).write_bytes(asset.encode())


# {
# 責務: [FakePixivApi: mimic the PixivPy3 methods used by the adapter]
# フィールド: [auth token observation, paginated payloads]
# }
class FakePixivApi:
    # {
    # 責務: [__init__: initialize request observations for endpoint tests]
    # 処理: [retain safe visibility and ranking parameters]
    # 引数: [None: test API setup]
    # 戻り値: [None: fake endpoint state initialized]
    # }
    def __init__(self):
        self.bookmark_restricts = []
        self.ranking_modes = []

    # {
    # 責務: [auth: return Pixiv-shaped successful authentication]
    # 処理: [provide the session identity without making network requests]
    # 引数: [refresh_token: ephemeral input]
    # 戻り値: [dict: API response]
    # }
    def auth(self, refresh_token):
        return {"response": {"user": {"id": "42"}}}

    # {
    # 責務: [user_detail: provide an authenticated identity payload]
    # 処理: [return a Pixiv-shaped current-user response]
    # 引数: [user_id: current user sentinel]
    # 戻り値: [dict: API response]
    # }
    def user_detail(self, user_id):
        return {"user": {"id": 42}}

    # {
    # 責務: [user_illusts: return a creator page for either illustration or manga mode]
    # 処理: [return one page then an empty cursor result]
    # 引数: [user_id: creator ID, type: selected work type, offset: current cursor]
    # 戻り値: [dict: API page]
    # }
    def user_illusts(self, user_id, type, offset):
        return {"illusts": [] if offset else [self._raw(101)]}

    # {
    # 責務: [user_bookmarks_illust: return one page with no following cursor]
    # 処理: [provide two pages and record the requested visibility]
    # 引数: [user_id: authenticated user, restrict: bookmark visibility, max_bookmark_id: cursor]
    # 戻り値: [dict: bookmark page]
    # }
    def user_bookmarks_illust(self, user_id, restrict, max_bookmark_id):
        self.bookmark_restricts.append(restrict)
        if max_bookmark_id is None:
            return {
                "illusts": [self._raw(101)],
                "next_url": "https://app-api.pixiv.net/v1/user/bookmarks/illust?max_bookmark_id=100",
            }
        return {"illusts": [self._raw(102)], "next_url": None}

    # {
    # 責務: [illust_ranking: return one page for an API ranking mode]
    # 処理: [record the API mode and return a bounded page]
    # 引数: [mode: Pixiv ranking mode, offset: page offset]
    # 戻り値: [dict: ranking page]
    # }
    def illust_ranking(self, mode, offset):
        self.ranking_modes.append(mode)
        return {"illusts": [] if offset else [self._raw(101)]}

    # {
    # 責務: [search_illust: return one normalized page fixture]
    # 処理: [return one work on the first offset and no later page]
    # 引数: [query: search term, search_target: API option, offset: page offset]
    # 戻り値: [dict: API response]
    # }
    def search_illust(self, query, search_target, offset):
        if offset:
            return {"illusts": []}
        return {"illusts": [self._raw(101)]}

    # {
    # 責務: [illust_detail: return API details for illustration or ugoira]
    # 処理: [mark the ugoira fixture and wrap the detail in Pixiv's response shape]
    # 引数: [work_id: numeric ID]
    # 戻り値: [dict: detail response]
    # }
    def illust_detail(self, work_id):
        raw = self._raw(work_id)
        raw["type"] = 2 if work_id == 202 else 0
        return {"illust": raw}

    # {
    # 責務: [ugoira_metadata: return archive URL and timed frames]
    # 処理: [provide one frame with a deterministic delay]
    # 引数: [work_id: numeric ID]
    # 戻り値: [dict: archive metadata]
    # }
    def ugoira_metadata(self, work_id):
        return {
            "ugoira_metadata": {
                "zip_urls": {"original": "https://i.pximg.net/ugoira.zip"},
                "frames": [{"file": "000000.jpg", "delay": 80}],
            }
        }

    # {
    # 責務: [_raw: build a minimal Pixiv API work object]
    # 処理: [include the metadata fields consumed by the adapter]
    # 引数: [work_id: numeric ID]
    # 戻り値: [dict: API work]
    # }
    @staticmethod
    def _raw(work_id):
        return {
            "id": work_id,
            "title": "test",
            "user": {"id": 42, "name": "author"},
            "type": 0,
            "page_count": 1,
            "tags": [{"name": "sky"}],
            "meta_single_page": {"original_image_url": "https://i.pximg.net/one.jpg"},
        }


if __name__ == "__main__":
    unittest.main()
