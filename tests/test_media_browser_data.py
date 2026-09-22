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


def collect(folder, collection="library", cancel=None):
    events = []
    media_scan.scan_folder(str(folder), collection, 1, cancel or threading.Event(), events.append)
    return tuple(item for event in events for item in event.items), events


class MediaDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "日本語 dir"
        create_samples(self.root)

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

    def test_stable_identity_across_scans_and_collection_changes(self):
        first, _ = collect(self.root)
        second, _ = collect(self.root, "generated")
        self.assertEqual({item.path: item.id for item in first}, {item.path: item.id for item in second})
        with self.assertRaises(dataclasses.FrozenInstanceError):
            first[0].name = "modified"

    def test_invalid_root_and_classification_are_errors(self):
        for folder, collection in ((self.root / "absent", "library"), (self.root, "bad"), ("", "library")):
            items, events = collect(folder, collection)
            self.assertEqual(items, ())
            self.assertEqual(events[-1].kind, "error")

    def test_cancelled_scan_publishes_nothing(self):
        cancel = threading.Event()
        cancel.set()
        items, events = collect(self.root, cancel=cancel)
        self.assertEqual((items, events), ((), []))

    def test_scan_has_explicit_count_limit(self):
        with mock.patch.object(media_scan, "MAX_ITEMS", 2):
            items, events = collect(self.root)
        self.assertEqual(len(items), 2)
        self.assertIn("上限", events[-1].message)

    def test_symlinks_are_not_followed_without_needing_symlink_privileges(self):
        entry = mock.Mock()
        entry.is_symlink.return_value = True
        context = mock.MagicMock()
        context.__enter__.return_value = iter([entry])
        with mock.patch.object(media_scan.os, "scandir", return_value=context):
            items, _ = collect(self.root)
        self.assertEqual(items, ())
        entry.is_dir.assert_not_called()

    def test_permission_errors_are_counted_and_do_not_abort_browser(self):
        with mock.patch.object(media_scan.os, "scandir", side_effect=PermissionError("denied")):
            items, events = collect(self.root)
        self.assertEqual(items, ())
        self.assertEqual(events[-1].kind, "done")
        self.assertIn("読み取れない", events[-1].message)

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

    def test_video_decode_and_position_preview(self):
        item = next(item for item in collect(self.root)[0] if item.kind == "video")
        reader = MediaPreviewReader()
        first, last = reader.read(item, 128), reader.read(item, 480, 1.0)
        self.assertFalse(first.error, first.error)
        self.assertFalse(last.error, last.error)
        self.assertEqual((first.width, first.height), (64, 48))
        self.assertAlmostEqual(first.duration, 1.0, places=1)
        self.assertNotEqual(first.png, last.png)

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

    def test_preview_validation_fails_safely(self):
        item = collect(self.root)[0][0]
        reader = MediaPreviewReader()
        for edge, fraction in ((100000, 0), (128, float("nan")), (128, -1)):
            self.assertTrue(reader.read(item, edge, fraction).error)


class MediaWorkerTests(unittest.TestCase):
    def test_load_is_async_replacement_is_latest_only_and_shutdown_works(self):
        io = media_io.MediaIO()
        entered, release = threading.Event(), threading.Event()
        seen = []
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
