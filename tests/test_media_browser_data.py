import dataclasses
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from PIL import Image
from comfyui_support_tools.applications.main_gui.data.processing import media_io, media_scan
from comfyui_support_tools.applications.main_gui.data.processing.media_preview_reader import MediaPreviewReader
from comfyui_support_tools.entrypoints.media_smoke import create_samples


# {
#   責務: [collect: runs the folder scanner and returns its records/events]
#   処理: [
#     1: invoke the media scanner with the supplied folder/collection/cancellation state,
#     2: return collected records and emitted events,
#   ],
#   引数: [
#     folder: folder scanned by the media browser (unspecified),
#     collection: media collection name (unspecified),
#     cancel: scan cancellation token (unspecified),
#   ],
#   戻り値: [result: tuple/list fixture built or selected by this helper]
# }
def collect(folder, collection="library", cancel=None):
    events = []
    media_scan.scan_folder(str(folder), collection, 1, cancel or threading.Event(), events.append)
    return tuple(item for event in events for item in event.items), events


# {
#   責務: [MediaDataTests: related test fixtures and cases for MediaData behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: [tmp: temporary root containing fixture files, root: fixture root or application root under test]
#   引数: []
# }
class MediaDataTests(unittest.TestCase):
    # {
    #   責務: [setUp: initializes per-test fixture state for MediaDataTests]
    #   処理: [
    #     1: create the per-test inputs and fixture resources required by the scenario,
    #     2: register cleanup for resources owned by the fixture,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "日本語 dir"
        create_samples(self.root)

    # {
    #   責務: [
    #     test_recursive_scan_and_supported_suffixes: verifies the behavior described by "recursive scan and supported suffixes",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for recursive scan and supported suffixes,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_recursive_scan_and_supported_suffixes(self):
        nested = self.root / "nested"
        nested.mkdir()
        Image.new("RGB", (10, 10)).save(nested / "extra.PNG")
        (nested / "notes.txt").write_text("not media")
        items, events = collect(self.root, "dataset")
        self.assertEqual(len(items), 5)
        self.assertEqual({item.collection for item in items}, {"dataset"})
        self.assertEqual({item.kind for item in items}, {"image", "video"})
        self.assertEqual(events[-1].kind, "done")
        self.assertTrue(all(Path(item.path).is_absolute() for item in items))

    # {
    #   責務: [
    #     test_stable_identity_across_scans_and_collection_changes: verifies the behavior described by "stable identity across scans and collection changes",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for stable identity across scans and collection changes,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_stable_identity_across_scans_and_collection_changes(self):
        first, _ = collect(self.root)
        second, _ = collect(self.root, "generated")
        self.assertEqual({item.path: item.id for item in first}, {item.path: item.id for item in second})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            first[0].name = "modified"

    # {
    #   責務: [
    #     test_invalid_root_and_classification_are_errors: verifies the behavior described by "invalid root and classification are errors",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for invalid root and classification are errors,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_invalid_root_and_classification_are_errors(self):
        for folder, collection in ((self.root / "absent", "library"), (self.root, "bad"), ("", "library")):
            items, events = collect(folder, collection)
            self.assertEqual(items, ())
            self.assertEqual(events[-1].kind, "error")

    # {
    #   責務: [
    #     test_cancelled_scan_publishes_nothing: verifies the behavior described by "cancelled scan publishes nothing",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for cancelled scan publishes nothing,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_cancelled_scan_publishes_nothing(self):
        cancel = threading.Event()
        cancel.set()
        items, events = collect(self.root, cancel=cancel)
        self.assertEqual((items, events), ((), []))

    # {
    #   責務: [test_scan_has_explicit_count_limit: verifies the behavior described by "scan has explicit count limit"]
    #   処理: [
    #     1: arrange case data and fixture state for scan has explicit count limit,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_scan_has_explicit_count_limit(self):
        with mock.patch.object(media_scan, "MAX_ITEMS", 2):
            items, events = collect(self.root)
        self.assertEqual(len(items), 2)
        self.assertIn("上限", events[-1].message)

    # {
    #   責務: [
    #     test_symlinks_are_not_followed_without_needing_symlink_privileges: verifies the behavior described by "symlinks are not followed without needing symlink privileges",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for symlinks are not followed without needing symlink privileges,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_symlinks_are_not_followed_without_needing_symlink_privileges(self):
        entry = mock.Mock()
        entry.is_symlink.return_value = True
        context = mock.MagicMock()
        context.__enter__.return_value = iter([entry])
        with mock.patch.object(media_scan.os, "scandir", return_value=context):
            items, _ = collect(self.root)
        self.assertEqual(items, ())
        entry.is_dir.assert_not_called()

    # {
    #   責務: [
    #     test_permission_errors_are_counted_and_do_not_abort_browser: verifies the behavior described by "permission errors are counted and do not abort browser",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for permission errors are counted and do not abort browser,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_permission_errors_are_counted_and_do_not_abort_browser(self):
        with mock.patch.object(media_scan.os, "scandir", side_effect=PermissionError("denied")):
            items, events = collect(self.root)
        self.assertEqual(items, ())
        self.assertEqual(events[-1].kind, "done")
        self.assertIn("読み取れない", events[-1].message)

    # {
    #   責務: [
    #     test_image_thumbnail_and_corrupt_file: verifies the behavior described by "image thumbnail and corrupt file",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for image thumbnail and corrupt file,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_image_thumbnail_and_corrupt_file(self):
        items, _ = collect(self.root)
        reader = MediaPreviewReader()
        item = next(item for item in items if item.name == "画像 sample.png")
        result = reader.read(item, 128)
        self.assertFalse(result.error)
        self.assertEqual((result.width, result.height), (160, 100))
        with Image.open(BytesIO(result.png)) as image:
            self.assertLessEqual(max(image.size), 128)
        broken = next(item for item in items if item.name == "broken.png")
        self.assertTrue(reader.read(broken, 128).error)

    # {
    #   責務: [
    #     test_video_decode_and_position_preview: verifies the behavior described by "video decode and position preview",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for video decode and position preview,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_video_decode_and_position_preview(self):
        item = next(item for item in collect(self.root)[0] if item.kind == "video")
        reader = MediaPreviewReader()
        first, last = reader.read(item, 128), reader.read(item, 480, 1.0)
        self.assertFalse(first.error, first.error)
        self.assertFalse(last.error, last.error)
        self.assertEqual((first.width, first.height), (64, 48))
        self.assertAlmostEqual(first.duration, 1.0, places=1)
        self.assertNotEqual(first.png, last.png)

    # {
    #   責務: [
    #     test_cache_hit_invalidation_and_size_bounds: verifies the behavior described by "cache hit invalidation and size bounds",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for cache hit invalidation and size bounds,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_cache_hit_invalidation_and_size_bounds(self):
        item = next(item for item in collect(self.root)[0] if item.name == "画像 sample.png")
        reader = MediaPreviewReader(max_entries=1, max_bytes=100_000)
        first = reader.read(item, 128)
        self.assertIs(reader.read(item, 128), first)
        Image.new("RGB", (25, 30)).save(item.path)
        second = reader.read(item, 128)
        self.assertNotEqual(first.png, second.png)
        self.assertEqual(second.width, 25)
        self.assertLessEqual(len(reader.cache), 1)
        limited = MediaPreviewReader(max_bytes=1)
        limited.read(item, 128)
        self.assertEqual(limited.cache_bytes, 0)
        Path(item.path).unlink()
        self.assertTrue(reader.read(item, 128).error)

    # {
    #   責務: [
    #     test_exif_orientation_and_pixel_limit: verifies the behavior described by "exif orientation and pixel limit",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for exif orientation and pixel limit,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    #   副作用: [一時directory内にfixture file/imageを作成・更新・削除する]
    # }
    def test_exif_orientation_and_pixel_limit(self):
        path = self.root / "rotation.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (80, 40)).save(path, exif=exif)
        item = next(item for item in collect(self.root)[0] if item.name == path.name)
        result = MediaPreviewReader().read(item, 128)
        self.assertEqual((result.width, result.height), (40, 80))
        from comfyui_support_tools.applications.main_gui.data.processing import media_preview_reader
        with mock.patch.object(media_preview_reader, "MAX_PIXELS", 100):
            self.assertTrue(MediaPreviewReader().read(item, 128).error)

    # {
    #   責務: [
    #     test_preview_validation_fails_safely: verifies the behavior described by "preview validation fails safely",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for preview validation fails safely,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_preview_validation_fails_safely(self):
        item = collect(self.root)[0][0]
        reader = MediaPreviewReader()
        for edge, fraction in ((100000, 0), (128, float("nan")), (128, -1)):
            self.assertTrue(reader.read(item, edge, fraction).error)


# {
#   責務: [MediaWorkerTests: related test fixtures and cases for MediaWorker behavior]
#   処理: [1: group related test cases and share their fixture state]
#   フィールド: []
#   引数: []
# }
class MediaWorkerTests(unittest.TestCase):
    # {
    #   責務: [
    #     test_load_is_async_replacement_is_latest_only_and_shutdown_works: verifies the behavior described by "load is async replacement is latest only and shutdown works",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for load is async replacement is latest only and shutdown works,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_load_is_async_replacement_is_latest_only_and_shutdown_works(self):
        io = media_io.MediaIO()
        entered, release = threading.Event(), threading.Event()
        seen = []
        # {
        #   責務: [scan: blocks on the supplied event and emits records for worker lifecycle tests]
        #   処理: [1: signal scan entry, 2: wait for cancellation/release and emit controlled records]
        #   引数: [
        #     folder: folder scanned by the media browser (unspecified),
        #     collection: media collection name (unspecified),
        #     token: scan identity token (unspecified),
        #     cancel: scan cancellation token (unspecified),
        #     emit: scan event callback (unspecified),
        #   ],
        #   戻り値: [None: test helper returns no value]
        # }
        def scan(folder, collection, token, cancel, emit):
            seen.append(folder)
            entered.set()
            release.wait(3)
        try:
            with mock.patch.object(media_io, "scan_folder", side_effect=scan):
                io.scan("first", "library")
                self.assertTrue(entered.wait(2))
                for i in range(10):
                    io.scan(str(i), "library")
                release.set()
                deadline = time.monotonic()+3
                while len(seen) < 2 and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(seen, ["first", "9"])
                self.assertEqual(len(io._threads), 2)
        finally:
            release.set()
            io.close()
            for worker in io._threads:
                worker.join(3)
                self.assertFalse(worker.is_alive())
        with self.assertRaises(RuntimeError):
            io.scan("after-close", "library")

    # {
    #   責務: [
    #     test_worker_queues_and_pending_decode_are_bounded: verifies the behavior described by "worker queues and pending decode are bounded",
    #   ],
    #   処理: [
    #     1: arrange case data and fixture state for worker queues and pending decode are bounded,
    #     2: exercise the application behavior, workflow, or UI action under test,
    #     3: verify its public result, state transition, error, or side-effect contract,
    #   ],
    #   引数: []
    #   戻り値: [None: test helper returns no value]
    # }
    def test_worker_queues_and_pending_decode_are_bounded(self):
        io = media_io.MediaIO()
        with mock.patch.object(io, "_start_workers"):
            io.thumbnails(1, tuple(range(10_000)))
        self.assertEqual(len(io._thumbnails), 60)
        self.assertEqual(io._scan_events.maxsize, 8)
        self.assertEqual(io._preview_events.maxsize, 72)
        io.close()


if __name__ == "__main__":
    unittest.main()
