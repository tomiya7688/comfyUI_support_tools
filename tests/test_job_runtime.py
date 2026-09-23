from pathlib import Path
import sys
import tempfile
from threading import Event, Thread
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image
from comfyui_support_tools.applications.main_gui.data.processing.action_io import ActionIO
from comfyui_support_tools.applications.main_gui.data.processing.job_runtime import JobRuntime
from comfyui_support_tools.applications.main_gui.data.processing.media_io import MediaIO
from comfyui_support_tools.shared.contracts.inspector_contracts import ActionRequest, TaggerSettings


def wait_for(predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


class JobRuntimeTests(unittest.TestCase):
    def test_lifecycle_progress_logs_times_backend_id_and_error(self):
        runtime = JobRuntime(max_concurrent=1)
        job = runtime.create(
            "generation",
            "Generate",
            source_ids=("a",),
            source_names=("image.png",),
        )
        before = runtime.snapshots()[0]
        self.assertEqual(before.state, "queued")
        self.assertIsNone(before.started_at)
        self.assertTrue(runtime.wait_start(job))
        runtime.update(job, 0.5, "half", "step 1")
        runtime.set_backend_job_id(job, "backend-123")
        middle = runtime.snapshots()[0]
        self.assertEqual(middle.state, "running")
        self.assertEqual(middle.progress, 0.5)
        self.assertEqual(middle.backend_job_id, "backend-123")
        self.assertIn("step 1", middle.logs)
        runtime.finish(job, "done", "complete")
        after = runtime.snapshots()[0]
        self.assertEqual(after.state, "done")
        self.assertEqual(after.progress, 1.0)
        self.assertIsNotNone(after.started_at)
        self.assertIsNotNone(after.finished_at)
        self.assertGreaterEqual(after.finished_at, after.started_at)

        failed = runtime.create("api", "Backend call")
        self.assertTrue(runtime.wait_start(failed))
        runtime.finish(failed, "error", "Backend disconnected", "HTTP timeout")
        error = next(item for item in runtime.snapshots() if item.id == failed)
        self.assertEqual(error.state, "error")
        self.assertIn("HTTP timeout", error.error)
        runtime.close()

    def test_concurrency_limit_keeps_second_queued_and_queued_cancel_wakes_waiter(self):
        runtime = JobRuntime(max_concurrent=1)
        cancel_one, cancel_two = Event(), Event()
        first = runtime.create("one", "first", cancel_event=cancel_one)
        second = runtime.create("two", "second", cancel_event=cancel_two)
        release = Event()
        results = {}

        def worker(job, release_event=None):
            results[job] = runtime.wait_start(job)
            if results[job] and release_event is not None:
                release_event.wait(3)
                runtime.finish(job, "done", "done")

        t1 = Thread(target=worker, args=(first, release))
        t2 = Thread(target=worker, args=(second,))
        t1.start()
        wait_for(lambda: next(item for item in runtime.snapshots() if item.id == first).state == "running")
        t2.start()
        wait_for(lambda: next(item for item in runtime.snapshots() if item.id == second).state == "queued")
        self.assertTrue(runtime.cancel(second))
        t2.join(2)
        self.assertFalse(t2.is_alive())
        self.assertFalse(results[second])
        self.assertTrue(cancel_two.is_set())
        release.set()
        t1.join(2)
        states = {item.id: item.state for item in runtime.snapshots()}
        self.assertEqual(states[first], "done")
        self.assertEqual(states[second], "cancelled")
        runtime.close()

    def test_running_cancel_is_cooperative_and_shutdown_never_waits(self):
        runtime = JobRuntime(max_concurrent=1)
        cancel = Event()
        job = runtime.create("slow", "slow io", cancel_event=cancel)
        self.assertTrue(runtime.wait_start(job))
        self.assertTrue(runtime.cancel(job))
        current = runtime.snapshots()[0]
        self.assertEqual(current.state, "running")
        self.assertTrue(cancel.is_set())
        self.assertIn("停止要求", current.message)
        start = time.monotonic()
        runtime.close()
        self.assertLess(time.monotonic() - start, 0.2)

    def test_history_is_bounded_and_progress_validation_is_strict(self):
        runtime = JobRuntime(max_concurrent=1, history_limit=10)
        for index in range(12):
            job = runtime.create("test", f"job {index}")
            self.assertTrue(runtime.wait_start(job))
            runtime.finish(job, "done")
        snapshots = runtime.snapshots()
        self.assertEqual(len(snapshots), 10)
        self.assertEqual(snapshots[0].action, "job 11")
        job = runtime.create("bad-progress", "bad")
        self.assertTrue(runtime.wait_start(job))
        for value in (-0.1, 1.1, float("nan")):
            with self.assertRaises(ValueError):
                runtime.update(job, value)
        runtime.finish(job, "cancelled")
        runtime.close()

    def test_contract_reserves_retry_lineage_without_claiming_handler(self):
        runtime = JobRuntime()
        original = runtime.create("tag", "tag", retryable=False)
        self.assertTrue(runtime.wait_start(original))
        runtime.finish(original, "error", error="temporary")
        retry = runtime.create("tag", "tag retry", retry_of=original, retryable=False)
        snapshot = next(item for item in runtime.snapshots() if item.id == retry)
        self.assertEqual(snapshot.retry_of, original)
        self.assertFalse(snapshot.retryable)
        runtime.cancel(retry)
        runtime.close()


class SharedExistingProcessJobTests(unittest.TestCase):
    def test_media_scan_and_tagger_actions_share_one_job_model(self):
        class FakeTransport:
            def probe(self, _settings):
                return ("fixture-model",)

            def tag(self, _item, _settings):
                return {"tags": {"fixture": 0.99}}

        runtime = JobRuntime(max_concurrent=2)
        media = MediaIO(runtime)
        action = ActionIO(FakeTransport(), runtime)
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                path = root / "画像.png"
                Image.new("RGB", (20, 20), "blue").save(path)
                media.scan(str(root), "library")
                media_items = []
                done = False
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not done:
                    for event in media.poll():
                        media_items.extend(event.items)
                        done = done or event.kind in ("done", "error")
                    time.sleep(0.01)
                self.assertTrue(done)
                self.assertEqual(len(media_items), 1)

                settings = TaggerSettings(
                    "http://127.0.0.1:1/pixai/v1/interrogate",
                    "fixture-model",
                )
                action.start(ActionRequest(1, "probe", settings))
                probe_done = False
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not probe_done:
                    probe_done = any(event.kind == "done" for event in action.poll())
                    time.sleep(0.01)
                self.assertTrue(probe_done)

                action.start(ActionRequest(2, "tag", settings, tuple(media_items)))
                tag_done = False
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not tag_done:
                    tag_done = any(event.kind == "done" for event in action.poll())
                    time.sleep(0.01)
                self.assertTrue(tag_done)

            snapshots = runtime.snapshots()
            kinds = {job.kind for job in snapshots}
            self.assertTrue({"media_scan", "tagger_probe", "tagger_tag"}.issubset(kinds))
            self.assertTrue(all(job.state == "done" for job in snapshots))
            tag = next(job for job in snapshots if job.kind == "tagger_tag")
            self.assertEqual(tag.progress, 1.0)
            self.assertEqual(tag.source_names, ("画像.png",))
            scan = next(job for job in snapshots if job.kind == "media_scan")
            self.assertIn("読込完了", scan.message)
        finally:
            action.close()
            media.close()
            runtime.close()


if __name__ == "__main__":
    unittest.main()
